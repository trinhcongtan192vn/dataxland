"""Telegram (spec 08, spec 05 §6.8).

Người dùng (cổng): tạo mã liên kết, xem và gỡ liên kết.
Bot (token nội bộ, `X-Service: bot`, `X-Telegram-Chat-Id`): đổi mã lấy liên kết, gỡ, báo bot bị xóa/chặn, ngữ cảnh
của chat, và dựng tin trả lời lệnh từ cùng bộ mẫu với trung tâm thông báo. Bot không có logic nghiệp vụ.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.context import AuthContext, bot_ctx_for_link, get_ctx, resolve_role
from app.auth.internal import ServiceCaller, require_service
from app.auth.permissions import require
from app.db import get_db
from app.db.models import (
    Membership,
    Report,
    ReportRecipient,
    TelegramLink,
    TelegramLinkCode,
    TelegramRate,
    Tenant,
    User,
)
from app.errors import ApiError
from app.metrics.key_numbers import key_numbers_scoped, number_text
from app.metrics.registry import get_registry
from app.notify.builders import week_no
from app.notify.dispatcher import hash_token
from app.notify.render import render
from app.notify.types import Button
from app.telegram.links import revoke_link
from dx_common.config import get_settings
from dx_common.events import publish
from dx_common.timeutil import now_utc

router = APIRouter(prefix="/v1/telegram", tags=["telegram"])

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_TTL = timedelta(minutes=10)
BAD_CODE_LIMIT, BAD_CODE_WINDOW, BAD_CODE_LOCK = 5, timedelta(minutes=10), timedelta(minutes=30)
LINK_ERRORS = {
    "CODE_INVALID": "mã không đúng",
    "CODE_EXPIRED": "mã đã dùng hoặc đã quá 10 phút",
    "CODE_WRONG_CHAT_TYPE": "mã này dành cho loại chat khác (chat riêng hoặc nhóm)",
    "ACCESS_LOST": "người tạo mã không còn quyền với shop",
    "LOCKED": "nhập sai mã quá nhiều lần, thử lại sau 30 phút",
}


def _code_hash(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


def _portal(path: str) -> str:
    return f"{get_settings().dx_public_base_url.rstrip('/')}{path}"


def _msg(name: str, data: dict[str, Any], buttons: list[Button] | None = None) -> dict[str, Any]:
    m = render(name, data, buttons)
    return {
        "text_html": m.telegram_html or m.text,
        "buttons": [{"label": b.label, "url": b.url, "callback_data": b.callback_data} for b in m.buttons],
    }


# --------------------------------------------------------------------------- người dùng (cổng)


class LinkCodeIn(BaseModel):
    kind: Literal["private", "group"] = "private"
    metric_scope: list[str] | None = None


class LinkCodeOut(BaseModel):
    code: str
    expires_at: datetime
    deep_link: str


class LinkOut(BaseModel):
    id: str
    chat_type: str
    chat_title: str | None
    tenant_id: str
    user_id: str
    metric_scope: list[str] | None
    linked_at: datetime
    mine: bool


@router.post("/link-codes", response_model=LinkCodeOut, status_code=201)
def create_link_code(
    body: LinkCodeIn, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)
) -> LinkCodeOut:
    if body.kind == "group":
        require(ctx, "telegram.link_group")
        reg = get_registry()
        scope = list(dict.fromkeys(body.metric_scope or []))
        visible = {m.metric for m in reg.visible_for_tenant(ctx.tenant)}
        if not scope or any(m not in visible for m in scope):
            raise ApiError(422, "SCOPE_INVALID", "Chọn ít nhất một chỉ số của gói cho nhóm")
    else:
        require(ctx, "telegram.link_self")
        scope = None
    code = "".join(secrets.choice(ALPHABET) for _ in range(8))
    exp = now_utc() + CODE_TTL
    db.add(
        TelegramLinkCode(
            code_hash=_code_hash(code),
            user_id=ctx.user_id or "",
            tenant_id=ctx.tenant_id,
            kind=body.kind,
            metric_scope=scope,
            expires_at=exp,
        )
    )
    bot = get_settings().telegram_bot_username
    param = "startgroup" if body.kind == "group" else "start"
    audit(
        db,
        action="telegram.code_created",
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        detail={"kind": body.kind},
    )
    return LinkCodeOut(code=code, expires_at=exp, deep_link=f"https://t.me/{bot}?{param}={code}")


@router.get("/links", response_model=list[LinkOut])
def my_links(ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> list[LinkOut]:
    require(ctx, "telegram.link_self")
    q = select(TelegramLink).where(TelegramLink.tenant_id == ctx.tenant_id, TelegramLink.status == "active")
    if ctx.role != "owner":
        q = q.where(TelegramLink.user_id == ctx.user_id)
    return [
        LinkOut(
            id=lk.id,
            chat_type=lk.chat_type,
            chat_title=lk.chat_title,
            tenant_id=lk.tenant_id,
            user_id=lk.user_id,
            metric_scope=list(lk.metric_scope) if lk.metric_scope else None,
            linked_at=lk.linked_at,
            mine=lk.user_id == ctx.user_id,
        )
        for lk in db.scalars(q.order_by(TelegramLink.linked_at.desc()))
    ]


@router.delete("/links/{link_id}", status_code=204)
def delete_link(link_id: str, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> None:
    require(ctx, "telegram.link_self")
    lk = db.get(TelegramLink, link_id)
    if lk is None or lk.tenant_id != ctx.tenant_id or lk.status != "active":
        raise ApiError(404, "LINK_NOT_FOUND", "Không tìm thấy liên kết")
    if lk.user_id != ctx.user_id and ctx.role != "owner":
        raise ApiError(403, "PERMISSION_DENIED", "Chỉ chủ shop gỡ được liên kết của người khác")
    revoke_link(db, lk, "user_unlink", ctx.user_id)


# --------------------------------------------------------------------------- bot


def _bot(caller: ServiceCaller) -> None:
    if caller.service != "bot":
        raise ApiError(403, "INTERNAL_ONLY", "Chỉ bot gọi được endpoint này")


def _chat(x_telegram_chat_id: str | None) -> int:
    try:
        return int(x_telegram_chat_id or "")
    except ValueError as exc:
        raise ApiError(400, "CHAT_ID_REQUIRED", "Thiếu X-Telegram-Chat-Id") from exc


def _limit(spec: str) -> tuple[int, timedelta]:
    n, _, secs = spec.partition("/")
    return int(n), timedelta(seconds=int(secs))


def _rate(db: Session, key: str, kind: str, limit: int, window: timedelta) -> int | None:
    """Cửa sổ trượt (spec 08 §6). Trả số phút phải chờ khi vượt, None khi còn lượt (và ghi một lượt)."""
    now = now_utc()
    since = now - window
    db.execute(
        delete(TelegramRate).where(
            TelegramRate.key == key, TelegramRate.kind == kind, TelegramRate.at < now - timedelta(days=1)
        )
    )
    rows = list(
        db.scalars(
            select(TelegramRate.at)
            .where(TelegramRate.key == key, TelegramRate.kind == kind, TelegramRate.at >= since)
            .order_by(TelegramRate.at)
        )
    )
    if len(rows) >= limit:
        wait = rows[0] + window - now
        return max(1, int(wait.total_seconds() // 60) + 1)
    db.add(TelegramRate(key=key, kind=kind, at=now))
    return None


def _active_links(db: Session, chat_id: int) -> list[TelegramLink]:
    return list(
        db.scalars(
            select(TelegramLink)
            .where(TelegramLink.chat_id == chat_id, TelegramLink.status == "active")
            .order_by(TelegramLink.linked_at)
        )
    )


class LinkIn(BaseModel):
    code: str
    chat_id: int
    chat_type: Literal["private", "group", "supergroup"]
    chat_title: str | None = None
    telegram_user_id: int | None = None


@router.post("/links")
def bot_link(
    body: LinkIn, caller: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)
) -> dict[str, Any]:
    _bot(caller)
    settings_url = _portal("/app/settings/telegram")
    key = str(body.chat_id)

    def fail(code: str) -> dict[str, Any]:
        db.add(TelegramRate(key=key, kind="bad_code", at=now_utc()))
        return {
            "ok": False,
            "error_code": code,
            "message": _msg("bot_link_error", {"reason_vi": LINK_ERRORS[code], "settings_url": settings_url}),
        }

    now = now_utc()
    recent = list(
        db.scalars(
            select(TelegramRate.at)
            .where(TelegramRate.key == key, TelegramRate.kind == "bad_code", TelegramRate.at >= now - BAD_CODE_LOCK)
            .order_by(TelegramRate.at)
        )
    )
    if _locked_run(recent):
        return {
            "ok": False,
            "error_code": "LOCKED",
            "message": _msg("bot_link_error", {"reason_vi": LINK_ERRORS["LOCKED"], "settings_url": settings_url}),
        }
    code = db.scalar(select(TelegramLinkCode).where(TelegramLinkCode.code_hash == _code_hash(body.code)))
    if code is None:
        return fail("CODE_INVALID")
    if code.used_at is not None or code.expires_at <= now:
        return fail("CODE_EXPIRED")
    if (code.kind == "private") != (body.chat_type == "private"):
        return fail("CODE_WRONG_CHAT_TYPE")
    if not _creator_has_access(db, code):
        return fail("ACCESS_LOST")
    existing = db.scalar(
        select(TelegramLink).where(
            TelegramLink.chat_id == body.chat_id,
            TelegramLink.tenant_id == code.tenant_id,
            TelegramLink.status == "active",
        )
    )
    if existing is not None:
        revoke_link(db, existing, "user_unlink")
    link = TelegramLink(
        chat_id=body.chat_id,
        chat_type=body.chat_type,
        chat_title=body.chat_title,
        telegram_user_id=body.telegram_user_id,
        user_id=code.user_id,
        tenant_id=code.tenant_id,
        metric_scope=code.metric_scope,
    )
    db.add(link)
    code.used_at = now
    db.flush()
    publish("telegram.linked", code.tenant_id, {"link_id": link.id, "chat_type": link.chat_type}, "s6b-bot", bind=db)
    audit(
        db,
        action="telegram.linked",
        tenant_id=code.tenant_id,
        actor_service="bot",
        target=link.id,
        detail={"chat_type": link.chat_type, "kind": code.kind},
    )
    t = db.get(Tenant, code.tenant_id)
    return {
        "ok": True,
        "tenant_id": code.tenant_id,
        "message": _msg("bot_link_ok", {"tenant_name": t.name if t else code.tenant_id}),
    }


def _creator_has_access(db: Session, code: TelegramLinkCode) -> bool:
    """Người tạo mã vẫn có quyền với khách; mã nhóm thì vẫn phải là owner (spec 08 §3.3)."""
    if code.kind == "group":
        m = db.scalar(
            select(Membership).where(Membership.user_id == code.user_id, Membership.tenant_id == code.tenant_id)
        )
        return m is not None and m.role == "owner"
    creator = db.get(User, code.user_id)
    if creator is None or creator.disabled:
        return False
    try:
        resolve_role(db, creator.id, creator.staff_role, code.tenant_id)
    except ApiError:
        return False
    return True


def _locked_run(times: list[datetime]) -> bool:
    """Có ít nhất 5 lần sai trong một cửa sổ 10 phút trong 30 phút gần nhất."""
    for i in range(len(times) - BAD_CODE_LIMIT + 1):
        if times[i + BAD_CODE_LIMIT - 1] - times[i] <= BAD_CODE_WINDOW:
            return True
    return False


class UnlinkIn(BaseModel):
    tenant_id: str | None = None  # None = mọi khách của chat


@router.post("/unlink")
def bot_unlink(
    body: UnlinkIn,
    caller: ServiceCaller = Depends(require_service),
    x_telegram_chat_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _bot(caller)
    chat = _chat(x_telegram_chat_id)
    links = [lk for lk in _active_links(db, chat) if body.tenant_id in (None, lk.tenant_id)]
    names = []
    for lk in links:
        t = db.get(Tenant, lk.tenant_id)
        names.append(t.name if t else lk.tenant_id)
        revoke_link(db, lk, "user_unlink")
    return {"unlinked": len(links), "message": _msg("bot_unlinked", {"tenant_names": ", ".join(names)})}


class ChatLeftIn(BaseModel):
    chat_id: int
    reason: Literal["bot_removed", "bot_blocked"]


@router.post("/chat-left")
def chat_left(
    body: ChatLeftIn, caller: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)
) -> dict[str, int]:
    _bot(caller)
    links = _active_links(db, body.chat_id)
    for lk in links:
        revoke_link(db, lk, body.reason)
    return {"unlinked": len(links)}


@router.get("/context")
def chat_context(
    caller: ServiceCaller = Depends(require_service),
    x_telegram_chat_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _bot(caller)
    chat = _chat(x_telegram_chat_id)
    out = []
    for lk in _active_links(db, chat):
        t = db.get(Tenant, lk.tenant_id)
        out.append(
            {
                "tenant_id": lk.tenant_id,
                "tenant_name": t.name if t else lk.tenant_id,
                "chat_type": lk.chat_type,
                "metric_scope": list(lk.metric_scope) if lk.metric_scope else None,
            }
        )
    return {"chat_id": chat, "links": out}


class MessageIn(BaseModel):
    tenant_id: str | None = None
    period: Literal["this_week", "this_month", "last_week", "last_month"] | None = None
    command: str | None = Field(default=None, max_length=32)
    free_text: bool = False


PERIOD_VI = {"this_week": "Tuần này", "this_month": "Tháng này", "last_week": "Tuần trước", "last_month": "Tháng trước"}
ACTION_VI = {
    "week": "xem số tuần này",
    "month": "xem số tháng này",
    "report": "xem báo cáo tuần",
    "unlink": "gỡ liên kết",
}


@router.post("/messages/{kind}")
def bot_message(
    kind: str,
    body: MessageIn,
    caller: ServiceCaller = Depends(require_service),
    x_telegram_chat_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _bot(caller)
    chat = _chat(x_telegram_chat_id)
    s = get_settings()
    if kind == "help":
        return _msg("bot_help", {"free_text_note": body.free_text, "ask_enabled": False, "portal_url": _portal("/app")})
    links = _active_links(db, chat)
    if kind == "not_linked" or not links:
        return _msg("bot_not_linked", {"settings_url": _portal("/app/settings/telegram")})
    n, window = _limit(s.tg_rate_commands)
    wait = _rate(db, str(chat), "command", n, window)
    if wait is not None:
        raise ApiError(
            429,
            "RATE_LIMITED",
            f"Thử lại sau {wait} phút",
            extra={"message": _msg("bot_rate_limited", {"minutes": wait})},
        )
    if body.tenant_id:
        links = [lk for lk in links if lk.tenant_id == body.tenant_id]
        if not links:
            return _msg("bot_not_linked", {"settings_url": _portal("/app/settings/telegram")})
    if len(links) > 1 or kind == "unlink_confirm":
        return _choose(db, links, kind, body)
    link = links[0]
    ctx = bot_ctx_for_link(db, link)
    if kind == "key_numbers":
        return _key_numbers_msg(db, ctx, link, body.period or "this_week")
    if kind == "latest_report":
        return _latest_report_msg(db, ctx, link)
    raise ApiError(404, "MESSAGE_KIND_UNKNOWN", f"Không có loại tin {kind}")


def _choose(db: Session, links: list[TelegramLink], kind: str, body: MessageIn) -> dict[str, Any]:
    cmd = body.command or {
        "key_numbers": "week" if (body.period or "this_week") == "this_week" else "month",
        "latest_report": "report",
    }.get(kind, "unlink")
    names = {lk.tenant_id: (t.name if (t := db.get(Tenant, lk.tenant_id)) else lk.tenant_id) for lk in links}
    if kind == "unlink_confirm":
        buttons = [Button(f"Gỡ {names[lk.tenant_id]}", callback_data=f"ku:{lk.tenant_id}") for lk in links]
        if len(links) > 1:
            buttons.append(Button("Gỡ tất cả", callback_data="ku:*"))
        target = names[links[0].tenant_id] if len(links) == 1 else "các shop đã liên kết"
        return _msg("bot_unlink_confirm", {"target_vi": target}, buttons)
    buttons = [Button(names[lk.tenant_id], callback_data=f"kt:{cmd}:{lk.tenant_id}") for lk in links]
    return _msg("bot_choose_tenant", {"action_vi": ACTION_VI.get(cmd, "xem số")}, buttons)


def _warning_short(w: dict[str, Any]) -> str:
    if w.get("code") == "MISSING_COGS":
        return str(w.get("detail_vi", "")).split(",")[0]
    return str(w.get("detail_vi", ""))


def _key_numbers_msg(db: Session, ctx: AuthContext, link: TelegramLink, period: str) -> dict[str, Any]:
    kn = key_numbers_scoped(ctx, period, db=db, caller="bot")
    scope = list(link.metric_scope) if link.metric_scope else (None if ctx.metric_scope == "all" else ctx.metric_scope)
    p = kn["period"]
    label = f"{PERIOD_VI[period]} ({p['from'][8:10]}/{p['from'][5:7]}–{p['to'][8:10]}/{p['to'][5:7]})"
    t = db.get(Tenant, ctx.tenant_id)
    note = "ngoài phạm vi của nhóm" if link.chat_type != "private" else "ngoài phạm vi được xem"
    numbers = [{"label_vi": n["label_vi"], "text": number_text(n, scope=scope, scope_note=note)} for n in kn["numbers"]]
    url = _portal(f"/app/dashboards/{ctx.pack}?t={ctx.tenant_id}")
    return _msg(
        "bot_key_numbers",
        {
            "period_label": label,
            "tenant_name": t.name if t else ctx.tenant_id,
            "numbers": numbers,
            "warnings": [_warning_short(w) for w in kn["warnings"]],
            "data_as_of": kn["data_as_of"],
        },
        [Button("Mở dashboard", url)],
    )


def _cmd_token(report_id: str, link_id: str) -> str:
    """Token mở báo cáo cho lệnh `/report`: tất định theo (báo cáo, liên kết) để không phải lưu token gốc."""
    key = (get_settings().internal_api_token or "dx-local").encode()
    return hmac.new(key, f"report-open:{report_id}:{link_id}".encode(), hashlib.sha256).hexdigest()


def _latest_report_msg(db: Session, ctx: AuthContext, link: TelegramLink) -> dict[str, Any]:
    t = db.get(Tenant, ctx.tenant_id)
    name = t.name if t else ctx.tenant_id
    r = db.scalar(
        select(Report)
        .where(Report.tenant_id == ctx.tenant_id, Report.status.in_(("sent", "partially_sent")))
        .order_by(Report.period_start.desc())
        .limit(1)
    )
    if r is None:
        return _msg("bot_latest_report", {"has_report": False, "tenant_name": name})
    token = _cmd_token(r.id, link.id)
    key = f"telegram_cmd:{link.chat_id}"
    rr = db.scalar(
        select(ReportRecipient).where(
            ReportRecipient.report_id == r.id,
            ReportRecipient.channel == "telegram",
            ReportRecipient.recipient_key == key,
        )
    )
    if rr is None:
        db.add(
            ReportRecipient(
                report_id=r.id,
                channel="telegram",
                recipient_key=key,
                user_id=link.user_id,
                telegram_link_id=link.id,
                open_token=hash_token(token),
            )
        )
    scope = list(link.metric_scope) if link.metric_scope else (None if ctx.metric_scope == "all" else ctx.metric_scope)
    nums = (r.snapshot.get("key_numbers") or {}).get("numbers", [])
    note = "ngoài phạm vi của nhóm" if link.chat_type != "private" else "ngoài phạm vi được xem"
    numbers = [{"label_vi": n["label_vi"], "text": number_text(n, scope=scope, scope_note=note)} for n in nums]
    url = _portal(f"/r/{token}")
    return _msg(
        "bot_latest_report",
        {
            "has_report": True,
            "tenant_name": name,
            "week_no": week_no(r.period_start),
            "week_range": f"{r.period_start:%d/%m}–{r.period_end:%d/%m}",
            "numbers": numbers,
            "data_as_of": r.snapshot.get("data_as_of"),
        },
        [Button("Xem báo cáo", url)],
    )


def count_active_links(db: Session, tenant_id: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(TelegramLink)
            .where(TelegramLink.tenant_id == tenant_id, TelegramLink.status == "active")
        )
        or 0
    )
