"""Trung tâm thông báo (FR-OPS-05, FR-OPS-08, NFR-12, spec 04 §5).

Nhận sự kiện, tra sổ đăng ký và `telegram_links` để biết người nhận, rồi gửi qua mọi kênh đã đăng ký mà hỗ trợ
người nhận đó. Thêm kênh mới là thêm adapter trong `notify/channels/`, không sửa file này.

- Bảng `notifications`, khóa duy nhất (`event_id`, `channel`, `recipient_key`) để không gửi trùng.
- Thử lại tối đa 3 lần, cách 1, 5, 15 phút. Một kênh lỗi không ảnh hưởng kênh khác.
- Telegram lỗi kết nối liên tục 30 phút → báo team qua email (không qua Telegram).
- Cảnh báo team: cùng (`tenant_id`, `type`, `reason`) trong 6 giờ chỉ gửi một tin.
- Khách chỉ nhận `report.ready` và `metric.anomaly`. Email luôn gửi cho `report.ready` (NFR-12).
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import (
    ChannelHealth,
    Membership,
    Notification,
    NotificationGroup,
    Report,
    ReportRecipient,
    TelegramLink,
    Tenant,
    User,
)
from app.notify.builders import Plan, build, tenant_name, week_no
from app.notify.channels import registered_channels
from app.notify.render import render
from app.notify.types import Button, Recipient, RenderedMessage
from dx_common.config import get_settings
from dx_common.events import Event
from dx_common.ids import new_ulid, random_token
from dx_common.logging import get_logger
from dx_common.tenants import TenantConfig
from dx_common.timeutil import now_utc

log = get_logger(__name__)

CONSUMER = "notify"
EVENT_TYPES = (
    "sync.failed",
    "test.failed",
    "metric.anomaly",
    "report.ready",
    "report.built",
    "decision.remeasure_due",
    "healthcheck.submitted",
    "healthcheck.completed",
    "healthcheck.failed",
    "tenant.created",
    "tenant.bootstrap_required",
    "tenant.config_invalid",
)
RETRY_DELAYS = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=15))
MAX_ATTEMPTS = 1 + len(RETRY_DELAYS)
GROUP_WINDOW = timedelta(hours=6)
TELEGRAM_OUTAGE = timedelta(minutes=30)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --------------------------------------------------------------------------- người nhận


def team_recipients() -> list[Recipient]:
    s = get_settings()
    out: list[Recipient] = []
    if s.telegram_team_chat_id:
        out.append(Recipient(kind="team", address=s.telegram_team_chat_id))
    for email in [e.strip() for e in s.dx_team_email.split(",") if e.strip()]:
        out.append(Recipient(kind="team", address=email))
    return out


def customer_recipients(db: Session, tenant_id: str, *, force_email: bool) -> list[Recipient]:
    t = db.get(Tenant, tenant_id)
    if t is None:
        return []
    cfg = TenantConfig.model_validate(t.config)
    out: list[Recipient] = []
    if "email" in cfg.notify.channels or force_email:
        emails = {e.lower() for e in cfg.notify.email}
        owner_rows = db.execute(
            select(User.id, User.email)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.tenant_id == tenant_id, Membership.role == "owner", User.disabled.is_(False))
        ).all()
        owner_ids = {e.lower(): uid for uid, e in owner_rows if e}
        emails |= set(owner_ids)
        for e in sorted(emails):
            out.append(Recipient(kind="email", address=e, tenant_id=tenant_id, user_id=owner_ids.get(e)))
    if "telegram" in cfg.notify.channels:
        for link in db.scalars(
            select(TelegramLink).where(TelegramLink.tenant_id == tenant_id, TelegramLink.status == "active")
        ):
            scope = tuple(link.metric_scope) if link.chat_type != "private" and link.metric_scope else None
            out.append(
                Recipient(
                    kind="telegram_chat",
                    address=str(link.chat_id),
                    tenant_id=tenant_id,
                    scope=scope,
                    user_id=link.user_id,
                    telegram_link_id=link.id,
                )
            )
    return out


def _channels_for(recipient: Recipient, allowed: set[str] | None = None) -> list[str]:
    return [
        name
        for name, ch in registered_channels().items()
        if (allowed is None or name in allowed) and ch.supports(recipient)
    ]


# --------------------------------------------------------------------------- xếp tin


def _queue(
    db: Session,
    ev: Event,
    channel: str,
    recipient: Recipient,
    msg: RenderedMessage,
    audience: str,
    report_recipient_id: str | None = None,
) -> None:
    stmt = (
        insert(Notification)
        .values(
            id=new_ulid(),
            event_id=ev.event_id,
            tenant_id=ev.tenant_id,
            channel=channel,
            recipient_key=recipient.key,
            audience=audience,
            template=msg.template,
            template_version=msg.template_version,
            message=msg.to_json(),
            status="pending",
            attempts=0,
            next_attempt_at=now_utc(),
            report_recipient_id=report_recipient_id,
        )
        .on_conflict_do_nothing(index_elements=["event_id", "channel", "recipient_key"])
    )
    db.execute(stmt)


def _group_allows(db: Session, ev: Event, reason: str) -> int | None:
    """Gộp cảnh báo team. Trả số lần đã gộp (để nêu trong tin) nếu được gửi, None nếu phải gộp."""
    key = f"{ev.tenant_id or '-'}|{ev.type}|{reason}"
    now = now_utc()
    g = db.get(NotificationGroup, key, with_for_update=True)
    if g is None:
        db.add(NotificationGroup(group_key=key, last_sent_at=now, suppressed_count=0))
        db.flush()
        return 0
    if now - g.last_sent_at < GROUP_WINDOW:
        g.suppressed_count += 1
        return None
    repeats = g.suppressed_count
    g.last_sent_at = now
    g.suppressed_count = 0
    return repeats


def _in_scope(recipient: Recipient, metrics: tuple[str, ...]) -> bool:
    return recipient.scope is None or all(m in recipient.scope for m in metrics)


def handle_event(db: Session, ev: Event) -> int:
    """Tạo bản ghi `notifications` cho một sự kiện. Trả số tin đã xếp."""
    if ev.type == "report.ready":
        return _report_ready(db, ev)
    queued = 0
    for plan in build(db, ev):
        if plan.audience == "team":
            repeats = _group_allows(db, ev, plan.group_reason or "") if plan.group_reason is not None else 0
            if repeats is None:
                continue
            data = {**plan.data, "repeat_count": repeats}
            msg = render(plan.template, data, plan.buttons)
            for r in team_recipients():
                for ch in _channels_for(r):
                    _queue(db, ev, ch, r, msg, "team")
                    queued += 1
        else:
            queued += _queue_customer(db, ev, plan)
    return queued


def _queue_customer(db: Session, ev: Event, plan: Plan) -> int:
    if not ev.tenant_id:
        return 0
    n = 0
    msg = render(plan.template, plan.data, plan.buttons)
    for r in customer_recipients(db, ev.tenant_id, force_email=False):
        if not _in_scope(r, plan.metrics):
            continue  # nhóm Telegram ngoài phạm vi chỉ số của tin cảnh báo
        # Email khách chỉ đi qua kênh email; chat Telegram chỉ qua kênh Telegram (theo `notify.channels`).
        for ch in _channels_for(r, {"email" if r.kind == "email" else "telegram"}):
            _queue(db, ev, ch, r, msg, "customer")
            n += 1
    return n


def report_message(db: Session, report: Report, url: str, recipient: Recipient | None) -> RenderedMessage:
    """Mẫu `report_ready` dùng chung cho mọi kênh và cho lệnh `/report` của bot (spec 06 §4.5, spec 08 §4)."""
    snap = report.snapshot or {}
    numbers = (snap.get("key_numbers") or {}).get("numbers", [])
    metric_keys = tuple(n.get("metric") or n["key"] for n in numbers)
    summary_only = recipient is not None and not _in_scope(recipient, metric_keys)
    start = report.period_start
    end = report.period_end
    data = {
        "tenant_name": tenant_name(db, report.tenant_id),
        "week_no": week_no(start),
        "week_range": f"{start:%d/%m}–{end:%d/%m}",
        "numbers": [
            {"label_vi": n["label_vi"], "value": n.get("value"), "unit": n["unit"], "change_pct": n.get("change_pct")}
            for n in numbers
        ],
        "summary_only": summary_only,
        "report_url": url,
    }
    return render("report_ready", data, [Button("Xem báo cáo", url)])


def _report_ready(db: Session, ev: Event) -> int:
    report = db.get(Report, ev.payload["report_id"])
    if report is None or report.status not in ("approved", "sent", "partially_sent"):
        return 0
    base = get_settings().dx_public_base_url.rstrip("/")
    n = 0
    for r in customer_recipients(db, report.tenant_id, force_email=True):
        channel = "email" if r.kind == "email" else "telegram"
        rr = db.scalar(
            select(ReportRecipient).where(
                ReportRecipient.report_id == report.id,
                ReportRecipient.channel == channel,
                ReportRecipient.recipient_key == r.key,
            )
        )
        if rr is not None:
            continue  # đã xếp (giao sự kiện lần hai)
        token = random_token(32)
        rr = ReportRecipient(
            report_id=report.id,
            channel=channel,
            recipient_key=r.key,
            user_id=r.user_id,
            telegram_link_id=r.telegram_link_id,
            open_token=hash_token(token),
        )
        db.add(rr)
        db.flush()
        msg = report_message(db, report, f"{base}/r/{token}", r)
        for ch in _channels_for(r, {channel}):
            _queue(db, ev, ch, r, msg, "customer", report_recipient_id=rr.id)
            n += 1
    return n


def process_event(db: Session, ev: Event) -> None:
    handle_event(db, ev)


# --------------------------------------------------------------------------- gửi


async def _send_all(items: list[tuple[str, Recipient, RenderedMessage]]) -> list[Any]:
    chans = registered_channels()

    async def one(ch: str, r: Recipient, m: RenderedMessage) -> Any:
        c = chans.get(ch)
        if c is None:
            from app.notify.types import DeliveryResult

            return DeliveryResult(ok=False, error_code="CHANNEL_NOT_REGISTERED", retryable=False)
        try:
            return await c.send(r, m)
        except Exception as exc:  # adapter không được làm hỏng vòng gửi
            from app.notify.types import DeliveryResult

            log.warning("kênh %s lỗi: %s", ch, type(exc).__name__)
            return DeliveryResult(ok=False, error_code=type(exc).__name__, connection_error=True)

    return list(await asyncio.gather(*(one(*it) for it in items)))


def _recipient_from_key(key: str) -> Recipient:
    kind, _, address = key.partition(":")
    return Recipient(kind=kind, address=address)  # type: ignore[arg-type]


def deliver_pending(db: Session, now: datetime | None = None, limit: int = 200) -> dict[str, int]:
    now = now or now_utc()
    rows = list(
        db.scalars(
            select(Notification)
            .where(Notification.status == "pending", Notification.next_attempt_at <= now)
            .order_by(Notification.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    if not rows:
        return {"sent": 0, "failed": 0, "retry": 0}
    items = [(n.channel, _recipient_from_key(n.recipient_key), RenderedMessage.from_json(n.message)) for n in rows]
    results = asyncio.run(_send_all(items))
    stats = {"sent": 0, "failed": 0, "retry": 0}
    touched_reports: set[str] = set()
    for n, res in zip(rows, results, strict=True):
        n.attempts += 1
        if res.ok:
            n.status, n.sent_at, n.error_code = "sent", now, None
            stats["sent"] += 1
        else:
            n.error_code = res.error_code
            if res.retryable and n.attempts < MAX_ATTEMPTS:
                n.next_attempt_at = now + RETRY_DELAYS[n.attempts - 1]
                stats["retry"] += 1
            else:
                n.status = "failed"
                stats["failed"] += 1
        _track_channel_health(db, n.channel, res.ok, bool(getattr(res, "connection_error", False)), now)
        if n.report_recipient_id:
            touched_reports.add(n.event_id)
        if not res.ok and n.channel == "telegram" and res.error_code == "TELEGRAM_FORBIDDEN":
            _bot_blocked(db, n)
    db.flush()
    for event_id in touched_reports:
        update_report_status(db, event_id, now)
    return stats


def _bot_blocked(db: Session, n: Notification) -> None:
    from app.telegram.links import revoke_link

    kind, _, address = n.recipient_key.partition(":")
    if kind != "telegram_chat" or not n.tenant_id:
        return
    link = db.scalar(
        select(TelegramLink).where(
            TelegramLink.chat_id == int(address), TelegramLink.tenant_id == n.tenant_id, TelegramLink.status == "active"
        )
    )
    if link is not None:
        revoke_link(db, link, "bot_blocked" if link.chat_type == "private" else "bot_removed")


def update_report_status(db: Session, event_id: str, now: datetime) -> None:
    rows = db.execute(
        select(Notification.status, func.min(Notification.report_recipient_id))
        .where(Notification.event_id == event_id, Notification.report_recipient_id.is_not(None))
        .group_by(Notification.status)
    ).all()
    statuses = {s for s, _ in rows}
    rr_id = next((x for _, x in rows if x), None)
    if not rr_id or "pending" in statuses:
        return
    rr = db.get(ReportRecipient, rr_id)
    report = db.get(Report, rr.report_id) if rr else None
    if report is None or report.status not in ("approved", "partially_sent", "sent"):
        return
    report.status = "partially_sent" if "failed" in statuses else "sent"
    report.sent_at = report.sent_at or now


def _track_channel_health(db: Session, channel: str, ok: bool, connection_error: bool, now: datetime) -> None:
    if channel != "telegram":
        return
    h = db.get(ChannelHealth, channel)
    if h is None:
        h = ChannelHealth(channel=channel)
        db.add(h)
    if ok:
        h.failing_since, h.alerted_at = None, None
        return
    if not connection_error:
        return
    if h.failing_since is None:
        h.failing_since = now
    elif now - h.failing_since >= TELEGRAM_OUTAGE and h.alerted_at is None:
        _alert_telegram_outage(db, h.failing_since, now)
        h.alerted_at = now


def _alert_telegram_outage(db: Session, since: datetime, now: datetime) -> None:
    msg = render("telegram_outage", {"since": since})
    ev_id = "tg-outage-" + since.strftime("%Y%m%d%H%M")
    for r in team_recipients():
        if "@" in r.address:
            db.execute(
                insert(Notification)
                .values(
                    id=new_ulid(),
                    event_id=ev_id,
                    channel="email",
                    recipient_key=r.key,
                    audience="team",
                    template=msg.template,
                    template_version=msg.template_version,
                    message=msg.to_json(),
                    status="pending",
                    attempts=0,
                    next_attempt_at=now,
                )
                .on_conflict_do_nothing(index_elements=["event_id", "channel", "recipient_key"])
            )


def run_once(db_factory: Any) -> dict[str, int]:
    """Một vòng worker: đọc sự kiện mới rồi gửi tin đến hạn (spec 04 §5, đọc mỗi 30 giây)."""
    from dx_common.events import consume

    def handler(ev: Event) -> None:
        with db_factory() as db:
            handle_event(db, ev)

    consumed = consume(CONSUMER, EVENT_TYPES, handler)
    with db_factory() as db:
        stats = deliver_pending(db)
    stats["events"] = consumed
    return stats
