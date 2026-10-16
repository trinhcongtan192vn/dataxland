"""Báo cáo tuần (spec 06 §4, FR-REP-01..07).

| Đường dẫn | Việc |
|---|---|
| `POST /v1/internal/reports/build` | Job `weekly_report` dựng bản nháp từ bộ máy chỉ số, ghi snapshot |
| `GET /v1/reports`, `/latest`, `/{id}` | Khách chỉ thấy báo cáo đã gửi; nhân viên thấy mọi trạng thái |
| `PUT /v1/reports/{id}` | Data lead viết nhận định (≤ 2.000 ký tự) và tối đa 5 việc cần làm khi còn `draft` |
| `POST /v1/reports/{id}/approve` | Khóa khi nhận định trống (`422 INSIGHT_REQUIRED`); phát `report.ready` |
| `POST /v1/reports/{id}/supersede` | Tạo bản mới cho cùng tuần, bản cũ `superseded` |
| `POST /v1/reports/{id}/resend` | Gửi lại cho người nhận bị lỗi |
| `GET /v1/reports/{id}/opens` | Người nhận, đã mở, mở lần đầu, kênh |
| `GET /v1/ops/reports` | Danh sách cho màn hình vận hành, mọi khách (spec 06 §4.4) |
| `GET /r/{token}` | Ghi nhận mở rồi chuyển hướng tới cổng; không cần đăng nhập (FR-REP-06) |
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.context import AuthContext, CurrentUser, get_ctx, get_current_user, internal_ctx
from app.auth.internal import ServiceCaller, require_service
from app.auth.permissions import require
from app.db import get_db
from app.db.models import Notification, Report, ReportOpen, ReportRecipient, Tenant, User
from app.errors import ApiError
from app.notify.dispatcher import hash_token
from app.reports.builder import TEMPLATE_VERSION, build_snapshot, last_week
from app.routers.ops import require_staff
from dx_common.config import get_settings
from dx_common.events import publish
from dx_common.timeutil import VN_TZ, now_utc, today_vn

router = APIRouter(tags=["reports"])

STAFF = ("data_lead", "engineer")
CUSTOMER_VISIBLE = ("sent", "partially_sent")
MAX_INSIGHT = 2000
MAX_ACTIONS = 5


class ReportSummary(BaseModel):
    id: str
    tenant_id: str
    tenant_name: str
    pack: str
    period_start: date
    period_end: date
    status: str
    data_stale: bool
    built_at: datetime
    approved_at: datetime | None
    sent_at: datetime | None
    recipients: int = 0
    opened: int = 0


class ReportOut(ReportSummary):
    snapshot: dict[str, Any]
    insight_md: str | None
    actions: list[str]
    insight_draft_md: str | None = None
    actions_draft: list[str] | None = None
    approved_by: str | None
    template_version: str | None
    superseded_by: str | None
    run_id: str | None


class ReportUpdate(BaseModel):
    insight_md: str | None = Field(default=None, max_length=MAX_INSIGHT)
    actions: list[str] | None = None

    @field_validator("actions")
    @classmethod
    def _actions(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        clean = [a.strip() for a in v if a.strip()]
        if len(clean) > MAX_ACTIONS:
            raise ValueError(f"Tối đa {MAX_ACTIONS} việc cần làm")
        if any("\n" in a or len(a) > 300 for a in clean):
            raise ValueError("Mỗi việc một dòng, tối đa 300 ký tự")
        return clean


class BuildIn(BaseModel):
    tenant_id: str
    period: str | None = None  # ngày thứ Hai đầu tuần; trống = tuần ISO trước
    run_id: str | None = None
    data_stale: bool = False


class OpenRow(BaseModel):
    recipient_id: str
    channel: str
    recipient: str
    opened: bool
    first_opened_at: datetime | None
    via: str | None
    delivery_status: str | None


def _counts(db: Session, report_ids: list[str]) -> dict[str, tuple[int, int]]:
    if not report_ids:
        return {}
    rec = dict(
        db.execute(
            select(ReportRecipient.report_id, func.count())
            .where(ReportRecipient.report_id.in_(report_ids))
            .group_by(ReportRecipient.report_id)
        ).all()
    )
    opened = dict(
        db.execute(
            select(ReportOpen.report_id, func.count(func.distinct(ReportOpen.recipient_id)))
            .where(ReportOpen.report_id.in_(report_ids), ReportOpen.recipient_id.is_not(None))
            .group_by(ReportOpen.report_id)
        ).all()
    )
    return {rid: (int(rec.get(rid, 0)), int(opened.get(rid, 0))) for rid in report_ids}


def _summary(r: Report, name: str, counts: tuple[int, int]) -> dict[str, Any]:
    return {
        "id": r.id,
        "tenant_id": r.tenant_id,
        "tenant_name": name,
        "pack": r.pack,
        "period_start": r.period_start,
        "period_end": r.period_end,
        "status": r.status,
        "data_stale": r.data_stale,
        "built_at": r.built_at,
        "approved_at": r.approved_at,
        "sent_at": r.sent_at,
        "recipients": counts[0],
        "opened": counts[1],
    }


def _out(db: Session, r: Report, staff: bool) -> ReportOut:
    t = db.get(Tenant, r.tenant_id)
    counts = _counts(db, [r.id]).get(r.id, (0, 0))
    approver = db.get(User, r.approved_by) if r.approved_by else None
    return ReportOut(
        **_summary(r, t.name if t else r.tenant_id, counts),
        snapshot=r.snapshot,
        insight_md=r.insight_md,
        actions=list(r.actions or []),
        insight_draft_md=r.insight_draft_md if staff else None,
        actions_draft=list(r.actions_draft or []) if staff and r.actions_draft else None,
        approved_by=(approver.display_name or approver.email) if approver else None,
        template_version=r.template_version,
        superseded_by=r.superseded_by,
        run_id=r.run_id,
    )


def _visible(ctx: AuthContext, r: Report) -> bool:
    return r.tenant_id == ctx.tenant_id and (ctx.role in STAFF or r.status in CUSTOMER_VISIBLE)


def _get(db: Session, ctx: AuthContext, report_id: str) -> Report:
    r = db.get(Report, report_id)
    if r is None or not _visible(ctx, r):
        raise ApiError(404, "REPORT_NOT_FOUND", "Không tìm thấy báo cáo")
    return r


# --------------------------------------------------------------------------- dựng


def build_report(
    db: Session, tenant_id: str, period_start: date | None, run_id: str | None, data_stale: bool
) -> dict[str, Any]:
    ctx = internal_ctx(db, tenant_id)
    if period_start is None:
        start, end = last_week(today_vn())
    else:
        start, end = period_start, period_start + timedelta(days=6)
    existing = db.scalar(
        select(Report).where(Report.tenant_id == tenant_id, Report.period_start == start, Report.status != "superseded")
    )
    if existing is not None and existing.status != "draft":
        return {"report_id": existing.id, "status": existing.status, "rebuilt": False}
    snap = build_snapshot(ctx, db, start, end, run_id=run_id, today=max(today_vn(), end + timedelta(days=1)))
    if existing is None:
        r = Report(
            tenant_id=tenant_id,
            pack=ctx.pack,
            period_start=start,
            period_end=end,
            status="draft",
            snapshot=snap,
            data_stale=data_stale,
            run_id=run_id,
            built_at=now_utc(),
            template_version=TEMPLATE_VERSION,
            actions=[],
        )
        db.add(r)
    else:  # bản nháp đã có: thay snapshot, giữ nhận định
        r = existing
        r.snapshot, r.data_stale, r.run_id, r.built_at = snap, data_stale, run_id, now_utc()
    db.flush()
    publish("report.built", tenant_id, {"report_id": r.id, "period": start.isoformat()}, "s6-reports", bind=db)
    audit(
        db,
        action="report.built",
        tenant_id=tenant_id,
        actor_service="dagster",
        target=r.id,
        detail={"data_stale": data_stale, "run_id": run_id},
    )
    return {"report_id": r.id, "status": r.status, "rebuilt": existing is not None}


@router.post("/v1/internal/reports/build")
def internal_build(
    body: BuildIn, _: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)
) -> dict[str, Any]:
    start = date.fromisoformat(body.period) if body.period else None
    if start is not None and start.weekday() != 0:
        raise ApiError(422, "PERIOD_NOT_MONDAY", "period phải là ngày thứ Hai đầu tuần")
    return build_report(db, body.tenant_id, start, body.run_id, body.data_stale)


# --------------------------------------------------------------------------- đọc


@router.get("/v1/reports", response_model=list[ReportSummary])
def list_reports(ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    require(ctx, "reports.read")
    q = select(Report).where(Report.tenant_id == ctx.tenant_id)
    if ctx.role not in STAFF:
        q = q.where(Report.status.in_(CUSTOMER_VISIBLE))
    rows = list(db.scalars(q.order_by(Report.period_start.desc(), Report.built_at.desc())))
    counts = _counts(db, [r.id for r in rows])
    t = db.get(Tenant, ctx.tenant_id)
    return [_summary(r, t.name if t else r.tenant_id, counts[r.id]) for r in rows]


@router.get("/v1/reports/latest", response_model=ReportOut)
def latest_report(ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> ReportOut:
    require(ctx, "reports.read")
    r = db.scalar(
        select(Report)
        .where(Report.tenant_id == ctx.tenant_id, Report.status.in_(CUSTOMER_VISIBLE))
        .order_by(Report.period_start.desc())
        .limit(1)
    )
    if r is None:
        raise ApiError(404, "REPORT_NOT_FOUND", "Chưa có báo cáo tuần nào được gửi")
    return _out(db, r, ctx.role in STAFF)


@router.get("/v1/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: str, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> ReportOut:
    require(ctx, "reports.read")
    r = _get(db, ctx, report_id)
    if ctx.role not in STAFF and ctx.user_id:
        _record_portal_open(db, r, ctx.user_id)
    return _out(db, r, ctx.role in STAFF)


def _record_portal_open(db: Session, r: Report, user_id: str) -> None:
    """Mở trong cổng: `via = portal`, một lần mỗi ngày mỗi người (spec 06 §4.6)."""
    start = datetime.combine(today_vn(), datetime.min.time(), tzinfo=VN_TZ)
    exists = db.scalar(
        select(ReportOpen.id).where(
            ReportOpen.report_id == r.id,
            ReportOpen.user_id == user_id,
            ReportOpen.via == "portal",
            ReportOpen.opened_at >= start,
        )
    )
    if exists:
        return
    rr = db.scalar(
        select(ReportRecipient.id).where(ReportRecipient.report_id == r.id, ReportRecipient.user_id == user_id).limit(1)
    )
    db.add(ReportOpen(report_id=r.id, recipient_id=rr, user_id=user_id, via="portal"))


@router.get("/v1/reports/{report_id}/opens", response_model=list[OpenRow])
def report_opens(
    report_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[OpenRow]:
    require_staff(user, "ops.read")
    if db.get(Report, report_id) is None:
        raise ApiError(404, "REPORT_NOT_FOUND", "Không tìm thấy báo cáo")
    out: list[OpenRow] = []
    for rr in db.scalars(
        select(ReportRecipient)
        .where(ReportRecipient.report_id == report_id)
        .order_by(ReportRecipient.channel, ReportRecipient.recipient_key)
    ):
        first = db.scalar(
            select(ReportOpen).where(ReportOpen.recipient_id == rr.id).order_by(ReportOpen.opened_at).limit(1)
        )
        note = db.scalar(select(Notification.status).where(Notification.report_recipient_id == rr.id).limit(1))
        kind, _, addr = rr.recipient_key.partition(":")
        shown = addr if kind == "email" else ("Telegram " + ("nhóm" if addr.startswith("-") else "chat riêng"))
        out.append(
            OpenRow(
                recipient_id=rr.id,
                channel=rr.channel,
                recipient=shown,
                opened=first is not None,
                first_opened_at=first.opened_at if first else None,
                via=first.via if first else None,
                delivery_status=note,
            )
        )
    return out


@router.get("/v1/ops/reports", response_model=list[ReportSummary])
def ops_reports(
    status: str | None = None,
    tenant_id: str | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    require_staff(user, "ops.read")
    q = select(Report, Tenant.name).join(Tenant, Tenant.tenant_id == Report.tenant_id)
    if status:
        q = q.where(Report.status == status)
    if tenant_id:
        q = q.where(Report.tenant_id == tenant_id)
    rows = db.execute(q.order_by(Report.period_start.desc(), Tenant.name).limit(300)).all()
    counts = _counts(db, [r.id for r, _ in rows])
    return [_summary(r, name, counts[r.id]) for r, name in rows]


# --------------------------------------------------------------------------- viết, duyệt, gửi


def _staff_ctx(db: Session, user: CurrentUser, report_id: str, action: str) -> Report:
    require_staff(user, action)
    r = db.get(Report, report_id)
    if r is None:
        raise ApiError(404, "REPORT_NOT_FOUND", "Không tìm thấy báo cáo")
    return r


@router.put("/v1/reports/{report_id}", response_model=ReportOut)
def edit_report(
    report_id: str, body: ReportUpdate, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> ReportOut:
    r = _staff_ctx(db, user, report_id, "reports.edit")
    if r.status != "draft":
        raise ApiError(409, "REPORT_LOCKED", "Báo cáo đã duyệt không sửa được; tạo bản mới cho cùng tuần")
    if body.insight_md is not None:
        r.insight_md = body.insight_md.strip() or None
    if body.actions is not None:
        r.actions = body.actions
    audit(db, action="report.edited", tenant_id=r.tenant_id, actor_user_id=user.id, target=r.id)
    db.flush()
    return _out(db, r, True)


@router.post("/v1/reports/{report_id}/approve", response_model=ReportOut)
def approve_report(
    report_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> ReportOut:
    r = _staff_ctx(db, user, report_id, "reports.approve")
    if r.status != "draft":
        raise ApiError(409, "REPORT_NOT_DRAFT", "Chỉ duyệt được bản nháp")
    if not (r.insight_md or "").strip():
        raise ApiError(422, "INSIGHT_REQUIRED", "Cần viết nhận định trước khi duyệt")
    r.status, r.approved_by, r.approved_at = "approved", user.id, now_utc()
    db.flush()
    publish(
        "report.ready", r.tenant_id, {"report_id": r.id, "period": r.period_start.isoformat()}, "s6-reports", bind=db
    )
    audit(db, action="report.approved", tenant_id=r.tenant_id, actor_user_id=user.id, target=r.id)
    return _out(db, r, True)


@router.post("/v1/reports/{report_id}/supersede", response_model=ReportOut)
def supersede_report(
    report_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> ReportOut:
    old = _staff_ctx(db, user, report_id, "reports.approve")
    if old.status in ("draft", "superseded"):
        raise ApiError(409, "REPORT_NOT_SUPERSEDABLE", "Chỉ thay được báo cáo đã duyệt hoặc đã gửi")
    old.status = "superseded"
    db.flush()
    new = Report(
        tenant_id=old.tenant_id,
        pack=old.pack,
        period_start=old.period_start,
        period_end=old.period_end,
        status="draft",
        snapshot=old.snapshot,
        insight_md=old.insight_md,
        actions=list(old.actions or []),
        data_stale=old.data_stale,
        run_id=old.run_id,
        built_at=now_utc(),
        template_version=old.template_version,
    )
    db.add(new)
    db.flush()
    old.superseded_by = new.id
    audit(
        db,
        action="report.superseded",
        tenant_id=old.tenant_id,
        actor_user_id=user.id,
        target=old.id,
        detail={"new_report_id": new.id},
    )
    return _out(db, new, True)


@router.post("/v1/reports/{report_id}/resend")
def resend_report(
    report_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict[str, int]:
    r = _staff_ctx(db, user, report_id, "reports.approve")
    rr_ids = list(db.scalars(select(ReportRecipient.id).where(ReportRecipient.report_id == r.id)))
    failed = list(
        db.scalars(
            select(Notification).where(Notification.report_recipient_id.in_(rr_ids), Notification.status == "failed")
        )
    )
    for n in failed:
        n.status, n.attempts, n.error_code, n.next_attempt_at = "pending", 0, None, now_utc()
    if failed and r.status == "partially_sent":
        r.status = "approved"
    audit(
        db,
        action="report.resend",
        tenant_id=r.tenant_id,
        actor_user_id=user.id,
        target=r.id,
        detail={"notifications": len(failed)},
    )
    return {"requeued": len(failed)}


# --------------------------------------------------------------------------- mở báo cáo


OpenVia = Literal["email_link", "telegram_button"]


@router.get("/r/{token}", include_in_schema=False)
def open_link(token: str, db: Session = Depends(get_db)) -> RedirectResponse:
    """Ghi nhận mở (kể cả khi chưa đăng nhập) rồi chuyển tới báo cáo trên cổng; token sai → trang chung."""
    base = get_settings().dx_public_base_url.rstrip("/")
    rr = db.scalar(select(ReportRecipient).where(ReportRecipient.open_token == hash_token(token)))
    r = db.get(Report, rr.report_id) if rr else None
    if rr is None or r is None:
        return RedirectResponse(f"{base}/report-link-invalid", status_code=302)
    via: OpenVia = "email_link" if rr.channel == "email" else "telegram_button"
    db.add(ReportOpen(report_id=r.id, recipient_id=rr.id, user_id=rr.user_id, via=via))
    target = r.superseded_by or r.id
    return RedirectResponse(f"{base}/app/reports/{target}?t={r.tenant_id}", status_code=302)
