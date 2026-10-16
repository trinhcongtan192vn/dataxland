"""Sensor `tenant_partitions` và `tenant_schedule` (spec 04 §3.1, §3.3)."""

from datetime import datetime, timedelta

import dagster as dg

from dx_common.timeutil import now_utc
from dx_pipelines.jobs.tenant_pipeline import tenant_pipeline
from dx_pipelines.jobs.weekly_report import weekly_report
from dx_pipelines.partitions import tenant_tags, tenants_partitions
from dx_pipelines.resources import active_tenants
from dx_pipelines.schedule import due_runs


@dg.sensor(minimum_interval_seconds=60, description="Đồng bộ partition với khách active và trial")
def tenant_partitions(context: dg.SensorEvaluationContext) -> dg.SensorResult:
    wanted = {t["tenant_id"] for t in active_tenants()}
    have = set(context.instance.get_dynamic_partitions("tenants"))
    reqs = []
    if wanted - have:
        reqs.append(tenants_partitions.build_add_request(sorted(wanted - have)))
    if have - wanted:
        reqs.append(tenants_partitions.build_delete_request(sorted(have - wanted)))
    return dg.SensorResult(dynamic_partitions_requests=reqs)


@dg.sensor(
    jobs=[tenant_pipeline, weekly_report],
    minimum_interval_seconds=60,
    description="Mở lần chạy theo schedule.sync và schedule.weekly_report của từng khách (FR-ING-06)",
)
def tenant_schedule(context: dg.SensorEvaluationContext) -> dg.SensorResult:
    now = now_utc()
    last = datetime.fromisoformat(context.cursor) if context.cursor else now - timedelta(minutes=1)
    tenants = active_tenants()
    have = set(context.instance.get_dynamic_partitions("tenants"))
    missing = sorted({t["tenant_id"] for t in tenants} - have)
    runs = []
    for d in due_runs(tenants, last, now):
        cfg = (
            {}
            if d.job == "tenant_pipeline"
            else {"ops": {"build_weekly_report": {"config": {"due_at": d.due_at.isoformat()}}}}
        )
        runs.append(
            dg.RunRequest(
                run_key=d.run_key,
                job_name=d.job,
                partition_key=d.tenant_id,
                tags=tenant_tags(d.tenant_id),
                run_config=cfg,
            )
        )
    return dg.SensorResult(
        run_requests=runs,
        dynamic_partitions_requests=[tenants_partitions.build_add_request(missing)] if missing else [],
        cursor=now.isoformat(),
    )
