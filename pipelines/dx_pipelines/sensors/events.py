"""Sensor `events`: tiêu thụ sự kiện cho Dagster, consumer `dagster` (spec 04 §3.5).

- `tenant.created` → `tenant_pipeline` nạp lịch sử.
- `healthcheck.submitted` → job `healthcheck`.
- `inputs.changed` → `tenant_pipeline` sau 10 phút không có thay đổi mới (gộp trong cursor).
- `pipeline.requested` (chạy lại từ màn hình vận hành), `identity.changed` (spec 10) → `tenant_pipeline`.
"""

import json
from datetime import datetime, timedelta
from typing import Any

import dagster as dg

from dx_common.events import Event, consume
from dx_common.timeutil import now_utc
from dx_pipelines.jobs.healthcheck import healthcheck
from dx_pipelines.jobs.tenant_pipeline import tenant_pipeline
from dx_pipelines.partitions import tenant_tags, tenants_partitions

CONSUMER = "dagster"
TYPES = ("tenant.created", "healthcheck.submitted", "inputs.changed", "pipeline.requested", "identity.changed")
DEBOUNCE = timedelta(minutes=10)


def plan_runs(
    events: list[Event], pending: dict[str, str], now: datetime
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Hàm thuần: từ sự kiện mới và danh sách chờ gộp, trả (lần chạy cần mở, danh sách chờ mới)."""
    runs: list[dict[str, Any]] = []
    pending = dict(pending)
    for ev in events:
        if ev.type == "inputs.changed" and ev.tenant_id:
            pending[ev.tenant_id] = max(pending.get(ev.tenant_id, ""), ev.occurred_at.isoformat())
        elif ev.type == "tenant.created" and ev.tenant_id:
            runs.append(
                {
                    "job": "tenant_pipeline",
                    "tenant_id": ev.tenant_id,
                    "key": f"created:{ev.event_id}",
                    "config": {"history": True},
                }
            )
        elif ev.type in ("pipeline.requested", "identity.changed") and ev.tenant_id:
            runs.append(
                {
                    "job": "tenant_pipeline",
                    "tenant_id": ev.tenant_id,
                    "key": f"{ev.type}:{ev.event_id}",
                    "config": {"full_refresh": bool(ev.payload.get("full_refresh"))},
                }
            )
        elif ev.type == "healthcheck.submitted":
            runs.append({"job": "healthcheck", "check_id": ev.payload["check_id"], "key": f"hc:{ev.event_id}"})
    for tid, last in list(pending.items()):
        if now - datetime.fromisoformat(last) >= DEBOUNCE:
            runs.append({"job": "tenant_pipeline", "tenant_id": tid, "key": f"inputs:{tid}:{last}", "config": {}})
            del pending[tid]
    return runs, pending


@dg.sensor(jobs=[tenant_pipeline, healthcheck], minimum_interval_seconds=30, description="Sự kiện cho Dagster")
def events_sensor(context: dg.SensorEvaluationContext) -> dg.SensorResult:
    state = json.loads(context.cursor) if context.cursor else {"pending": {}}
    batch: list[Event] = []
    consume(CONSUMER, TYPES, batch.append)
    runs, pending = plan_runs(batch, state.get("pending", {}), now_utc())
    have = set(context.instance.get_dynamic_partitions("tenants"))
    add: set[str] = set()
    reqs = []
    for r in runs:
        if r["job"] == "healthcheck":
            reqs.append(
                dg.RunRequest(
                    run_key=r["key"],
                    job_name="healthcheck",
                    run_config={"ops": {"healthcheck_op": {"config": {"check_id": r["check_id"]}}}},
                    tags={"dx/healthcheck": r["check_id"]},
                )
            )
            continue
        if r["tenant_id"] not in have:
            add.add(r["tenant_id"])
        reqs.append(
            dg.RunRequest(
                run_key=r["key"],
                job_name="tenant_pipeline",
                partition_key=r["tenant_id"],
                tags=tenant_tags(r["tenant_id"]),
                run_config={"ops": {"run_tenant_pipeline": {"config": r["config"]}}},
            )
        )
    return dg.SensorResult(
        run_requests=reqs,
        cursor=json.dumps({"pending": pending}),
        dynamic_partitions_requests=[tenants_partitions.build_add_request(sorted(add))] if add else [],
    )
