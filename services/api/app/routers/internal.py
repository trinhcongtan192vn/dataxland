"""Endpoint nội bộ (spec 05 §6.10). Chỉ dịch vụ nội bộ gọi; Caddy chặn `/v1/internal/` từ bên ngoài."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.auth.internal import ServiceCaller, require_service
from app.db import get_db
from app.db.models import PipelineRun, SourceSync, Tenant
from app.errors import ApiError
from dx_common.events import EVENT_TYPES, publish
from dx_common.ids import new_ulid
from dx_common.timeutil import now_utc

router = APIRouter(tags=["internal"])


class InternalTenant(BaseModel):
    tenant_id: str
    name: str
    status: str
    pack: str
    dataset_prefix: str
    bootstrap_required: bool
    config: dict[str, Any]
    config_hash: str


@router.get("/v1/internal/tenants", response_model=list[InternalTenant])
def internal_tenants(
    status: list[str] | None = Query(default=None),
    _: ServiceCaller = Depends(require_service),
    db: Session = Depends(get_db),
) -> list[InternalTenant]:
    q = select(Tenant).order_by(Tenant.tenant_id)
    if status:
        q = q.where(Tenant.status.in_(status))
    return [
        InternalTenant(
            tenant_id=t.tenant_id,
            name=t.name,
            status=t.status,
            pack=t.pack,
            dataset_prefix=f"t_{t.tenant_id}",
            bootstrap_required=t.bootstrap_required,
            config=t.config,
            config_hash=t.config_hash,
        )
        for t in db.scalars(q)
    ]


class EventIn(BaseModel):
    type: str
    tenant_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    producer: str


class EventOut(BaseModel):
    event_id: str


@router.post("/v1/events", response_model=EventOut, status_code=201)
def post_event(
    body: EventIn, caller: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)
) -> EventOut:
    if body.type not in EVENT_TYPES:
        raise ApiError(400, "EVENT_UNKNOWN", f"Loại sự kiện không có trong danh mục: {body.type}")
    try:
        eid = publish(body.type, body.tenant_id, body.payload, body.producer or caller.service, bind=db)
    except ValueError as exc:
        raise ApiError(400, "EVENT_PAYLOAD_INVALID", str(exc)[:300]) from exc
    return EventOut(event_id=eid)


class SourceStatusIn(BaseModel):
    source: str
    account_id: str = ""
    status: Literal["running", "success", "failed", "skipped"]
    error_code: str | None = None
    rows_loaded: int | None = None


class RunIn(BaseModel):
    run_id: str
    tenant_id: str
    job: str
    status: Literal["running", "success", "blocked", "failed"]
    step: str | None = None
    step_status: Literal["running", "success", "failed", "skipped", "warning"] | None = None
    failed_step: str | None = None
    blocking_failures: list[dict[str, Any]] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    data_as_of: datetime | None = None
    sources: list[SourceStatusIn] = Field(default_factory=list)


@router.post("/v1/internal/runs", status_code=204)
def record_run(body: RunIn, _: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)) -> None:
    """Dagster ghi trạng thái lần chạy và nguồn sau mỗi bước (spec 04 §3.2, §6)."""
    now = now_utc()
    run = db.get(PipelineRun, body.run_id)
    if run is None:
        run = PipelineRun(
            run_id=body.run_id,
            tenant_id=body.tenant_id,
            job=body.job,
            status=body.status,
            started_at=body.started_at or now,
            steps={},
        )
        db.add(run)
    run.status = body.status
    if body.step and body.step_status:
        steps = dict(run.steps or {})
        steps[body.step] = {"status": body.step_status, "at": now.isoformat()}
        run.steps = steps
    if body.failed_step:
        run.failed_step = body.failed_step
    if body.blocking_failures is not None:
        run.blocking_failures = body.blocking_failures
    if body.finished_at or body.status in ("success", "blocked", "failed"):
        run.finished_at = body.finished_at or now
    if body.data_as_of:
        run.data_as_of = body.data_as_of
    for s in body.sources:
        stmt = insert(SourceSync).values(
            tenant_id=body.tenant_id,
            source=s.source,
            account_id=s.account_id,
            last_attempt_at=now,
            last_status=s.status,
            last_error_code=s.error_code,
            rows_loaded=s.rows_loaded,
            last_success_at=now if s.status == "success" else None,
            id=new_ulid(),
        )
        upd: dict[str, Any] = {
            "last_attempt_at": now,
            "last_status": s.status,
            "last_error_code": s.error_code,
            "updated_at": now,
        }
        if s.rows_loaded is not None:
            upd["rows_loaded"] = s.rows_loaded
        if s.status == "success":
            upd["last_success_at"] = now
        db.execute(stmt.on_conflict_do_update(index_elements=["tenant_id", "source", "account_id"], set_=upd))


class LatestRunIn(BaseModel):
    tenant_id: str
    status: str = "success"
    since: datetime | None = None
    job: str = "tenant_pipeline"


@router.post("/v1/internal/runs/latest")
def latest_run(
    body: LatestRunIn, _: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Lần chạy gần nhất theo trạng thái, cho job `weekly_report` chờ dữ liệu mới (spec 04 §3.3)."""
    q = select(PipelineRun).where(
        PipelineRun.tenant_id == body.tenant_id, PipelineRun.job == body.job, PipelineRun.status == body.status
    )
    if body.since:
        q = q.where(PipelineRun.started_at >= body.since)
    r = db.scalar(q.order_by(PipelineRun.started_at.desc()).limit(1))
    if r is None:
        return {}
    return {"run_id": r.run_id, "started_at": r.started_at, "finished_at": r.finished_at, "data_as_of": r.data_as_of}


class CleanupIn(BaseModel):
    older_than_days: int = Field(default=90, ge=7)


@router.post("/v1/internal/events/cleanup")
def events_cleanup(
    body: CleanupIn, _: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)
) -> dict[str, int]:
    """Xóa sự kiện đã được mọi consumer xử lý và cũ hơn N ngày (spec 04 §3.4)."""
    from datetime import timedelta

    from sqlalchemy import delete, exists

    from dx_common.events.tables import event_dead_letters, event_processed, events

    cutoff = now_utc() - timedelta(days=body.older_than_days)
    stale = select(events.c.event_id).where(events.c.occurred_at < cutoff)
    pending_dead = exists().where(
        event_dead_letters.c.event_id == events.c.event_id, event_dead_letters.c.dead.is_(False)
    )
    res = db.execute(delete(events).where(events.c.event_id.in_(stale), ~pending_dead))
    db.execute(delete(event_processed).where(event_processed.c.processed_at < cutoff))
    return {"deleted": int(getattr(res, "rowcount", 0) or 0)}


class AnomalyRunIn(BaseModel):
    tenant_id: str
    run_id: str | None = None


@router.post("/v1/internal/anomalies/run")
def anomalies_run(
    body: AnomalyRunIn, _: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Phát hiện bất thường sau khi làm mới Cube (spec 03 §8, spec 04 §3.2 bước `detect_anomalies`)."""
    from app.auth.context import internal_ctx
    from app.metrics.anomaly import detect

    ctx = internal_ctx(db, body.tenant_id)
    events = detect(ctx, db)
    return {"tenant_id": body.tenant_id, "anomalies": len(events), "metrics": [e["metric"] for e in events]}
