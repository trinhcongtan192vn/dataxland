"""Phát hiện bất thường (FR-MET-07, spec 03 §8).

Với mỗi chỉ số có khối `anomaly` và thuộc gói của khách: so giá trị của kỳ gần nhất đã đủ ngày (`grain: day` → hôm qua;
`grain: week` → tuần trước) với trung bình 4 kỳ cùng loại trước đó (ngày cùng thứ trong 4 tuần trước; 4 tuần trước).
Lệch tuyệt đối quá `threshold_pct` → phát `metric.anomaly`. Khóa (`tenant_id`, `metric`, `grain`, `period`) chỉ phát
một lần. Không chạy khi lần chạy gần nhất đang bị chặn bởi test.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.auth.context import AuthContext
from app.db.models import MetricAnomaly, PipelineRun
from app.metrics.engine import QueryIn, query
from app.metrics.registry import get_registry
from dx_common.events import publish
from dx_common.timeutil import today_vn, week_start


def latest_run_blocked(db: Session, tenant_id: str) -> bool:
    r = db.scalar(
        select(PipelineRun)
        .where(PipelineRun.tenant_id == tenant_id, PipelineRun.job == "tenant_pipeline")
        .order_by(PipelineRun.started_at.desc())
        .limit(1)
    )
    return r is not None and r.status == "blocked"


def _value(ctx: AuthContext, metric: str, start: date, end: date, db: Session) -> Decimal | None:
    res = query(
        ctx,
        QueryIn(metrics=[metric], time={"from": start.isoformat(), "to": end.isoformat()}),
        db=db,
        caller="anomaly",
        allow_hidden=True,
    )
    v = res["rows"][0].get(metric) if res["rows"] else None
    return None if v is None else Decimal(str(v))


def detect(ctx: AuthContext, db: Session, *, today: date | None = None) -> list[dict[str, Any]]:
    if latest_run_blocked(db, ctx.tenant_id):
        return []
    t = today or today_vn()
    reg = get_registry()
    events: list[dict[str, Any]] = []
    for m in reg.metrics.values():
        if not m.anomaly or not reg.tenant_eligible(m, ctx.tenant):
            continue
        grain = m.anomaly.get("grain", "week")
        threshold = Decimal(str(m.anomaly.get("threshold_pct", 30))) / 100
        if grain == "day":
            cur_start = cur_end = t - timedelta(days=1)
            prior = [(cur_start - timedelta(days=7 * k), cur_start - timedelta(days=7 * k)) for k in range(1, 5)]
            period = cur_start.isoformat()
        else:
            cur_start = week_start(t) - timedelta(days=7)
            cur_end = cur_start + timedelta(days=6)
            prior = [(cur_start - timedelta(days=7 * k), cur_end - timedelta(days=7 * k)) for k in range(1, 5)]
            period = cur_start.isoformat()
        exists = db.get(MetricAnomaly, (ctx.tenant_id, m.metric, grain, period))
        if exists is not None:
            continue
        value = _value(ctx, m.metric, cur_start, cur_end, db)
        base_vals = [_value(ctx, m.metric, a, b, db) for a, b in prior]
        base_known = [v for v in base_vals if v is not None]
        if value is None or len(base_known) < 4:
            continue
        baseline = sum(base_known, Decimal(0)) / Decimal(len(base_known))
        if baseline == 0:
            continue
        diff = (value - baseline) / abs(baseline)
        if abs(diff) <= threshold:
            continue
        good = (diff > 0 and m.good_direction == "up") or (diff < 0 and m.good_direction == "down")
        payload = {
            "metric": m.metric,
            "version": m.version,
            "grain": grain,
            "period": period,
            "value": float(value),
            "baseline": float(baseline),
            "diff_pct": round(float(diff), 4),
            "direction": "good" if good else "bad",
        }
        eid = publish("metric.anomaly", ctx.tenant_id, payload, "s2-metrics", bind=db)
        db.execute(
            insert(MetricAnomaly)
            .values(
                tenant_id=ctx.tenant_id,
                metric=m.metric,
                grain=grain,
                period=period,
                event_id=eid,
                value=value,
                baseline=baseline,
                diff_pct=diff,
            )
            .on_conflict_do_nothing()
        )
        events.append({**payload, "event_id": eid})
    return events
