"""Nhật ký quyết định (spec 06 §7, FR-DEC-01, FR-DEC-02).

- Tạo: API tự lấy `baseline_value` qua bộ máy chỉ số cho cửa sổ ngay trước `decided_on` (7 hoặc 28 ngày), ghi kèm
  `metric_version`, phát `decision.logged`.
- Đo lại: `POST /v1/decisions/{id}/measure` tính `after_value` cho cửa sổ cùng độ dài bắt đầu từ `decided_on`.
- Nhắc: `POST /v1/internal/decisions/remind` (job `decision_reminders`, 08:00) phát `decision.remeasure_due` cho
  quyết định đến hạn, mỗi quyết định một lần.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.context import AuthContext, get_ctx
from app.auth.internal import ServiceCaller, require_service
from app.auth.permissions import require
from app.db import get_db
from app.db.models import Decision
from app.errors import ApiError
from app.metrics.engine import FilterIn, QueryIn, check_metric, query
from dx_common.events import publish
from dx_common.timeutil import now_utc, today_vn

router = APIRouter(tags=["decisions"])

Window = Literal["last_7_days", "last_28_days"]
WINDOW_DAYS = {"last_7_days": 7, "last_28_days": 28}
Conclusion = Literal["achieved", "not_achieved", "inconclusive"]


class DecisionIn(BaseModel):
    decided_on: date
    title: str = Field(min_length=1, max_length=200)
    detail_md: str | None = Field(default=None, max_length=5000)
    decided_by: str = Field(min_length=1, max_length=120)
    metric: str
    dimension_filter: list[FilterIn] = Field(default_factory=list)
    baseline_window: Window = "last_7_days"
    target_value: Decimal | None = None
    remeasure_on: date


class DecisionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    detail_md: str | None = Field(default=None, max_length=5000)
    decided_by: str | None = Field(default=None, min_length=1, max_length=120)
    target_value: Decimal | None = None
    remeasure_on: date | None = None
    after_value: Decimal | None = None
    conclusion: Conclusion | None = None
    conclusion_md: str | None = Field(default=None, max_length=5000)


class DecisionOut(BaseModel):
    id: str
    decided_on: date
    title: str
    detail_md: str | None
    decided_by: str
    metric: str
    metric_name_vi: str
    metric_unit: str
    metric_version: str
    dimension_filter: list[dict[str, Any]]
    baseline_window: str
    baseline_from: date
    baseline_to: date
    baseline_value: float | None
    target_value: float | None
    remeasure_on: date
    after_from: date
    after_to: date
    after_value: float | None
    after_measured_at: datetime | None
    conclusion: str | None
    conclusion_md: str | None
    due: bool
    created_at: datetime


def baseline_range(decided_on: date, window: str) -> tuple[date, date]:
    n = WINDOW_DAYS[window]
    return decided_on - timedelta(days=n), decided_on - timedelta(days=1)


def after_range(decided_on: date, window: str) -> tuple[date, date]:
    n = WINDOW_DAYS[window]
    return decided_on, decided_on + timedelta(days=n - 1)


def _value(
    ctx: AuthContext, db: Session, metric: str, start: date, end: date, filters: list[FilterIn]
) -> Decimal | None:
    body = QueryIn(metrics=[metric], time={"from": start.isoformat(), "to": end.isoformat()}, filters=filters)
    res = query(ctx, body, db=db, caller="decisions")
    v = res["rows"][0].get(metric) if res["rows"] else None
    return None if v is None else Decimal(str(v))


def _f(v: Decimal | None) -> float | None:
    return None if v is None else float(v)


def _out(d: Decision) -> DecisionOut:
    from app.metrics.registry import get_registry

    m = get_registry().get(d.metric)
    b0, b1 = baseline_range(d.decided_on, d.baseline_window)
    a0, a1 = after_range(d.decided_on, d.baseline_window)
    return DecisionOut(
        id=d.id,
        decided_on=d.decided_on,
        title=d.title,
        detail_md=d.detail_md,
        decided_by=d.decided_by,
        metric=d.metric,
        metric_name_vi=m.name_vi if m else d.metric,
        metric_unit=m.unit if m else "count",
        metric_version=d.metric_version,
        dimension_filter=list(d.dimension_filter or []),
        baseline_window=d.baseline_window,
        baseline_from=b0,
        baseline_to=b1,
        baseline_value=_f(d.baseline_value),
        target_value=_f(d.target_value),
        remeasure_on=d.remeasure_on,
        after_from=a0,
        after_to=a1,
        after_value=_f(d.after_value),
        after_measured_at=d.after_measured_at,
        conclusion=d.conclusion,
        conclusion_md=d.conclusion_md,
        due=d.remeasure_on <= today_vn() and d.conclusion is None,
        created_at=d.created_at,
    )


def _get(db: Session, ctx: AuthContext, decision_id: str) -> Decision:
    d = db.get(Decision, decision_id)
    if d is None or d.tenant_id != ctx.tenant_id:
        raise ApiError(404, "DECISION_NOT_FOUND", "Không tìm thấy quyết định")
    return d


@router.get("/v1/decisions", response_model=list[DecisionOut])
def list_decisions(ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> list[DecisionOut]:
    require(ctx, "decisions.read")
    rows = db.scalars(
        select(Decision)
        .where(Decision.tenant_id == ctx.tenant_id)
        .order_by(Decision.decided_on.desc(), Decision.created_at.desc())
    )
    return [_out(d) for d in rows]


@router.post("/v1/decisions", response_model=DecisionOut, status_code=201)
def create_decision(
    body: DecisionIn, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)
) -> DecisionOut:
    require(ctx, "decisions.write")
    m = check_metric(ctx, body.metric)
    if body.remeasure_on < body.decided_on:
        raise ApiError(422, "REMEASURE_BEFORE_DECISION", "Ngày đo lại phải sau ngày quyết định")
    b0, b1 = baseline_range(body.decided_on, body.baseline_window)
    baseline = _value(ctx, db, m.metric, b0, b1, body.dimension_filter)
    d = Decision(
        tenant_id=ctx.tenant_id,
        decided_on=body.decided_on,
        title=body.title,
        detail_md=body.detail_md,
        decided_by=body.decided_by,
        metric=m.metric,
        metric_version=m.version,
        dimension_filter=[f.model_dump(exclude_none=True) for f in body.dimension_filter],
        baseline_window=body.baseline_window,
        baseline_value=baseline,
        target_value=body.target_value,
        remeasure_on=body.remeasure_on,
        created_by=ctx.user_id,
    )
    db.add(d)
    db.flush()
    publish("decision.logged", ctx.tenant_id, {"decision_id": d.id}, "s5-api", bind=db)
    audit(db, action="decision.created", tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, target=d.id)
    db.refresh(d)
    return _out(d)


@router.get("/v1/decisions/{decision_id}", response_model=DecisionOut)
def get_decision(decision_id: str, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> DecisionOut:
    require(ctx, "decisions.read")
    return _out(_get(db, ctx, decision_id))


@router.put("/v1/decisions/{decision_id}", response_model=DecisionOut)
def update_decision(
    decision_id: str, body: DecisionUpdate, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)
) -> DecisionOut:
    require(ctx, "decisions.write")
    d = _get(db, ctx, decision_id)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(d, k, v)
    if "after_value" in data:
        d.after_measured_at = now_utc()
    if d.remeasure_on < d.decided_on:
        raise ApiError(422, "REMEASURE_BEFORE_DECISION", "Ngày đo lại phải sau ngày quyết định")
    audit(
        db,
        action="decision.updated",
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        target=d.id,
        detail={"fields": sorted(data)},
    )
    db.flush()
    return _out(d)


@router.post("/v1/decisions/{decision_id}/measure", response_model=DecisionOut)
def measure_decision(
    decision_id: str, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)
) -> DecisionOut:
    require(ctx, "decisions.write")
    d = _get(db, ctx, decision_id)
    check_metric(ctx, d.metric)
    a0, a1 = after_range(d.decided_on, d.baseline_window)
    if a1 >= today_vn():
        raise ApiError(409, "TOO_EARLY", f"Chưa đủ dữ liệu: cửa sổ sau quyết định kết thúc ngày {a1:%d/%m/%Y}")
    filters = [FilterIn.model_validate(f) for f in d.dimension_filter or []]
    d.after_value = _value(ctx, db, d.metric, a0, a1, filters)
    d.after_measured_at = now_utc()
    audit(db, action="decision.measured", tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, target=d.id)
    db.flush()
    return _out(d)


@router.post("/v1/internal/decisions/remind")
def remind_due(_: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)) -> dict[str, Any]:
    today = today_vn()
    due = db.scalars(
        select(Decision).where(
            Decision.remeasure_on <= today, Decision.reminded_at.is_(None), Decision.conclusion.is_(None)
        )
    )
    ids: list[str] = []
    for d in due:
        publish("decision.remeasure_due", d.tenant_id, {"decision_id": d.id}, "s5-api", bind=db)
        d.reminded_at = now_utc()
        ids.append(d.id)
    return {"reminded": len(ids), "decision_ids": ids}
