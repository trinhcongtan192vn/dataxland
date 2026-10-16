"""Chỉ số: `POST /v1/metrics/query`, `GET /v1/metrics`, `GET /v1/metrics/key-numbers`, `GET /v1/metrics/flags`
(spec 03 §4, §5, §7; spec 05 §6.2). Mọi số đi qua đây; web, bot, báo cáo không tự tính chỉ số."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.context import AuthContext, get_ctx
from app.auth.permissions import require
from app.db import get_db
from app.errors import ApiError
from app.metrics.engine import QueryIn, check_metric, query, visible_metrics
from app.metrics.flags import compute_flags
from app.metrics.key_numbers import key_numbers_scoped
from app.metrics.registry import get_registry

router = APIRouter(prefix="/v1/metrics", tags=["metrics"])


class MetricMeta(BaseModel):
    name_vi: str
    version: str
    unit: str


class QueryOut(BaseModel):
    query_id: str
    tenant_id: str
    time: dict[str, Any]
    metrics: dict[str, MetricMeta]
    rows: list[dict[str, Any]]
    data_as_of: str | None
    warnings: list[dict[str, Any]]


@router.post("/query", response_model=QueryOut)
def metrics_query(body: QueryIn, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    require(ctx, "metrics.read")
    return query(ctx, body, db=db, caller=ctx.caller)


class MetricInfo(BaseModel):
    metric: str
    name_vi: str
    description_vi: str
    version: str
    type: str
    unit: str
    good_direction: str
    packs: list[str]
    requires: list[str]
    dimensions: list[dict[str, str]]
    time_grains: list[str]
    formula_vi: str | None = None
    source_note_vi: str | None = None
    synonyms_vi: list[str] = []
    history: list[dict[str, Any]] = []


def _info(name: str) -> MetricInfo:
    reg = get_registry()
    m = reg.get(name)
    assert m is not None
    hb = m.handbook or {}
    return MetricInfo(
        metric=m.metric,
        name_vi=m.name_vi,
        description_vi=m.description_vi,
        version=m.version,
        type=m.type,
        unit=m.unit,
        good_direction=m.good_direction,
        packs=list(m.packs),
        requires=list(m.requires),
        dimensions=[{"name": d, "name_vi": str(reg.dimensions.get(d, {}).get("name_vi", d))} for d in m.dimensions],
        time_grains=list(m.time_grains),
        formula_vi=hb.get("formula_vi"),
        source_note_vi=hb.get("source_note_vi"),
        synonyms_vi=list(m.synonyms_vi),
        history=list(hb.get("history", [])),
    )


@router.get("", response_model=list[MetricInfo])
def list_metrics(ctx: AuthContext = Depends(get_ctx)) -> list[MetricInfo]:
    """Chỉ số người gọi được xem, kèm dữ liệu sổ tay (spec 03 §4.5, FR-DSH-04)."""
    require(ctx, "metrics.read")
    return [_info(m.metric) for m in sorted(visible_metrics(ctx), key=lambda x: (x.packs, x.name_vi))]


@router.get("/key-numbers")
def get_key_numbers(
    period: str = Query(default="last_week"), ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)
) -> dict[str, Any]:
    require(ctx, "metrics.read")
    return key_numbers_scoped(ctx, period, db=db)


@router.get("/flags")
def get_flags(ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    require(ctx, "metrics.read")
    if ctx.pack != "agency":
        return []
    return compute_flags(ctx, db=db)


@router.get("/{metric}", response_model=MetricInfo)
def get_metric(metric: str, ctx: AuthContext = Depends(get_ctx)) -> MetricInfo:
    require(ctx, "metrics.read")
    try:
        check_metric(ctx, metric)
    except ApiError as exc:
        if exc.code == "METRIC_UNKNOWN":
            raise ApiError(404, "METRIC_UNKNOWN", f"Không có chỉ số {metric}") from exc
        raise
    return _info(metric)
