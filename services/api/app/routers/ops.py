"""Màn hình vận hành (FR-OPS-04, spec 05 §6.9, spec 04 §6).

`GET /v1/ops/overview` ghép `pipeline_runs`, `source_syncs`, `reports`, `report_opens` thành một dòng mỗi khách.
Dữ liệu ghi ngay khi bước kết thúc nên độ trễ dưới 5 phút.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.context import CurrentUser, build_ctx, get_current_user
from app.auth.permissions import allowed, require
from app.db import get_db
from app.db.models import (
    FxManualRate,
    IdentityMatch,
    PartnerGrant,
    PipelineRun,
    Report,
    ReportOpen,
    ReportRecipient,
    SourceSync,
    Tenant,
    TenantCost,
    TenantHours,
)
from app.errors import ApiError
from dx_common.events import publish
from dx_common.ids import new_ulid
from dx_common.tenants import TenantConfig
from dx_common.timeutil import month_start, now_utc, today_vn, week_start

router = APIRouter(prefix="/v1", tags=["ops"])


def require_staff(user: CurrentUser, action: str) -> None:
    """Quyền `/ops` không gắn với một khách: kiểm theo vai trò nhân viên (spec 05 §4)."""
    if not user.staff_role or not allowed(user.staff_role, action):
        raise ApiError(403, "PERMISSION_DENIED", "Chỉ nhân viên DataxLand vào được màn hình vận hành")


class SourceCell(BaseModel):
    source: str
    account_id: str
    connector: str
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_status: str | None
    last_error_code: str | None
    color: str  # green | yellow | red | grey


class ReportCell(BaseModel):
    report_id: str | None
    period_start: date | None
    status: str  # not_built | draft | approved | sent | partially_sent | failed
    recipients: int = 0
    opened: int = 0
    first_opened_at: datetime | None = None


class OverviewRow(BaseModel):
    tenant_id: str
    name: str
    pack: str
    status: str
    bootstrap_required: bool
    sources: list[SourceCell]
    last_run: dict[str, Any] | None
    blocking_tests: int
    warning_tests: int
    weekly_report: ReportCell
    pending_matches: int
    source_count: int
    partner_count: int
    costs_month_vnd: int | None = None
    hours_month: float | None = None


def _color(sync: SourceSync | None, freshness_h: int, now: datetime) -> str:
    if sync is None or sync.last_attempt_at is None:
        return "grey"
    if sync.last_status == "failed":
        return "red"
    if sync.last_success_at and now - sync.last_success_at <= timedelta(hours=freshness_h):
        return "green"
    return "yellow"


def report_cell(db: Session, tenant_id: str) -> ReportCell:
    target = week_start(today_vn()) - timedelta(days=7)
    r = db.scalar(
        select(Report)
        .where(Report.tenant_id == tenant_id, Report.status != "superseded")
        .order_by(Report.period_start.desc())
        .limit(1)
    )
    if r is None or r.period_start < target:
        return ReportCell(report_id=None, period_start=target, status="not_built")
    recips = db.scalar(select(func.count()).select_from(ReportRecipient).where(ReportRecipient.report_id == r.id)) or 0
    opened = db.execute(
        select(func.count(func.distinct(ReportOpen.recipient_id)), func.min(ReportOpen.opened_at)).where(
            ReportOpen.report_id == r.id, ReportOpen.recipient_id.is_not(None)
        )
    ).one()
    return ReportCell(
        report_id=r.id,
        period_start=r.period_start,
        status=r.status,
        recipients=int(recips),
        opened=int(opened[0] or 0),
        first_opened_at=opened[1],
    )


@router.get("/ops/overview", response_model=list[OverviewRow])
def overview(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> list[OverviewRow]:
    require_staff(user, "ops.read")
    now = now_utc()
    month = month_start(today_vn())
    out: list[OverviewRow] = []
    for t in db.scalars(select(Tenant).where(Tenant.status != "archived").order_by(Tenant.tenant_id)):
        cfg = TenantConfig.model_validate(t.config)
        syncs = {
            (s.source, s.account_id): s
            for s in db.scalars(select(SourceSync).where(SourceSync.tenant_id == t.tenant_id))
        }
        cells = []
        for src in cfg.enabled_sources():
            sy = syncs.get((src.type, src.account_id or ""))
            cells.append(
                SourceCell(
                    source=src.type,
                    account_id=src.account_id or "",
                    connector=src.connector,
                    last_attempt_at=sy.last_attempt_at if sy else None,
                    last_success_at=sy.last_success_at if sy else None,
                    last_status=sy.last_status if sy else None,
                    last_error_code=sy.last_error_code if sy else None,
                    color=_color(sy, cfg.quality.freshness_hours or 8, now),
                )
            )
        run = db.scalar(
            select(PipelineRun)
            .where(PipelineRun.tenant_id == t.tenant_id, PipelineRun.job == "tenant_pipeline")
            .order_by(PipelineRun.started_at.desc())
            .limit(1)
        )
        blocking = len(run.blocking_failures or []) if run and run.status == "blocked" else 0
        warns = (
            sum(1 for v in (run.steps or {}).values() if isinstance(v, dict) and v.get("status") == "warning")
            if run
            else 0
        )
        pending = (
            db.scalar(
                select(func.count())
                .select_from(IdentityMatch)
                .where(IdentityMatch.tenant_id == t.tenant_id, IdentityMatch.status == "proposed")
            )
            or 0
        )
        cost = db.scalar(
            select(func.sum(TenantCost.amount_vnd)).where(
                TenantCost.tenant_id == t.tenant_id, TenantCost.month == month
            )
        )
        hours = db.scalar(
            select(TenantHours.hours).where(TenantHours.tenant_id == t.tenant_id, TenantHours.month == month)
        )
        partners = (
            db.scalar(
                select(func.count())
                .select_from(PartnerGrant)
                .where(PartnerGrant.tenant_id == t.tenant_id, PartnerGrant.revoked_at.is_(None))
            )
            or 0
        )
        out.append(
            OverviewRow(
                tenant_id=t.tenant_id,
                name=t.name,
                pack=t.pack,
                status=t.status,
                bootstrap_required=t.bootstrap_required,
                sources=cells,
                last_run={
                    "run_id": run.run_id,
                    "status": run.status,
                    "started_at": run.started_at,
                    "finished_at": run.finished_at,
                    "failed_step": run.failed_step,
                    "data_as_of": run.data_as_of,
                }
                if run
                else None,
                blocking_tests=blocking,
                warning_tests=warns,
                weekly_report=report_cell(db, t.tenant_id),
                pending_matches=int(pending),
                source_count=len([s for s in cfg.enabled_sources() if s.type != "portal"]),
                partner_count=int(partners),
                costs_month_vnd=int(cost) if cost is not None else None,
                hours_month=float(hours) if hours is not None else None,
            )
        )
    return out


class RunOut(BaseModel):
    run_id: str
    job: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    failed_step: str | None
    blocking_failures: list[dict[str, Any]] | None
    steps: dict[str, Any]
    data_as_of: datetime | None
    triage_md: str | None


@router.get("/ops/tenants/{tenant_id}/runs", response_model=list[RunOut])
def tenant_runs(
    tenant_id: str,
    limit: int = Query(default=30, le=200),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RunOut]:
    ctx = build_ctx(db, user, tenant_id)
    require(ctx, "ops.read")
    rows = db.scalars(
        select(PipelineRun)
        .where(PipelineRun.tenant_id == tenant_id)
        .order_by(PipelineRun.started_at.desc())
        .limit(limit)
    )
    return [
        RunOut(
            run_id=r.run_id,
            job=r.job,
            status=r.status,
            started_at=r.started_at,
            finished_at=r.finished_at,
            failed_step=r.failed_step,
            blocking_failures=r.blocking_failures,
            steps=r.steps or {},
            data_as_of=r.data_as_of,
            triage_md=r.triage_md,
        )
        for r in rows
    ]


class RerunIn(BaseModel):
    full_refresh: bool = False
    reason: str | None = Field(default=None, max_length=300)


@router.post("/ops/tenants/{tenant_id}/runs", status_code=202)
def rerun(
    tenant_id: str, body: RerunIn, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict[str, str]:
    """Yêu cầu chạy lại `tenant_pipeline`: phát sự kiện nội bộ cho Dagster (spec 05 §6.9)."""
    ctx = build_ctx(db, user, tenant_id)
    require(ctx, "ops.write")
    eid = publish(
        "pipeline.requested",
        tenant_id,
        {"requested_by": user.id, "full_refresh": body.full_refresh, "reason": body.reason},
        "s4-ops",
        bind=db,
    )
    audit(
        db,
        action="ops.rerun_requested",
        tenant_id=tenant_id,
        actor_user_id=user.id,
        target=eid,
        detail=body.model_dump(),
    )
    return {"event_id": eid}


@router.get("/ops/tenants/{tenant_id}/sources")
def tenant_sources(
    tenant_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    ctx = build_ctx(db, user, tenant_id)
    require(ctx, "ops.read")
    return [
        {
            "source": s.source,
            "account_id": s.account_id,
            "last_attempt_at": s.last_attempt_at,
            "last_success_at": s.last_success_at,
            "last_status": s.last_status,
            "last_error_code": s.last_error_code,
            "rows_loaded": s.rows_loaded,
            "connected_at": s.connected_at,
        }
        for s in db.scalars(select(SourceSync).where(SourceSync.tenant_id == tenant_id))
    ]


class FxIn(BaseModel):
    date: date
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    rate_vnd: Decimal = Field(gt=0, max_digits=18, decimal_places=4)


@router.post("/admin/fx-rates", status_code=201)
def manual_fx(
    body: FxIn, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Nhập tỷ giá tay vào `fx_manual_rates`; connector `fx_vcb` ghép vào `dx_ref.fx_rates` (spec 05 §6.9)."""
    require_staff(user, "ops.write")
    stmt = insert(FxManualRate).values(
        id=new_ulid(), date=body.date, currency=body.currency, rate_vnd=body.rate_vnd, created_by=user.id
    )
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=["date", "currency"],
            set_={"rate_vnd": body.rate_vnd, "created_by": user.id, "updated_at": now_utc()},
        )
    )
    audit(
        db,
        action="fx.manual_rate",
        actor_user_id=user.id,
        target=f"{body.date}:{body.currency}",
        detail={"rate_vnd": str(body.rate_vnd)},
    )
    return {"date": str(body.date), "currency": body.currency, "rate_vnd": str(body.rate_vnd)}


@router.get("/admin/fx-rates")
def list_manual_fx(
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    require_staff(user, "ops.read")
    return [
        {"date": str(r.date), "currency": r.currency, "rate_vnd": str(r.rate_vnd)}
        for r in db.scalars(select(FxManualRate).order_by(FxManualRate.date.desc()).limit(200))
    ]


class HoursIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    hours: Decimal = Field(ge=0, max_digits=8, decimal_places=2)
    note: str | None = None


@router.put("/ops/tenants/{tenant_id}/hours", status_code=204)
def set_hours(
    tenant_id: str, body: HoursIn, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    """Giờ người theo khách, nhập tay (FR-OPS-06)."""
    ctx = build_ctx(db, user, tenant_id)
    require(ctx, "ops.write")
    y, m = body.month.split("-")
    stmt = insert(TenantHours).values(
        id=new_ulid(),
        month=date(int(y), int(m), 1),
        tenant_id=tenant_id,
        hours=body.hours,
        note=body.note,
        created_by=user.id,
    )
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=["month", "tenant_id"],
            set_={"hours": body.hours, "note": body.note, "updated_at": now_utc()},
        )
    )
