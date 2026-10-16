"""Job cố định (spec 04 §3.4): `fx_daily`, `sync_tenants`, `healthcheck_cleanup`, `decision_reminders`,
`events_cleanup`."""

import os
from typing import Any

import dagster as dg

from dx_pipelines.api_client import ApiClient


@dg.op
def fx_daily_op(context: dg.OpExecutionContext) -> dict[str, Any]:
    from connectors.fx_vcb.source import run_fx_daily

    res = run_fx_daily()
    context.log.info(str(res))
    return res


@dg.job(description="Tỷ giá Vietcombank hằng ngày (spec 01 §6)")
def fx_daily() -> None:
    fx_daily_op()


@dg.op
def sync_tenants_op(context: dg.OpExecutionContext) -> dict[str, Any]:
    """`git fetch` thư mục tenants/ (nếu bật) rồi đồng bộ vào Postgres (spec 04 §1.3)."""
    import subprocess
    import sys

    from dx_pipelines.dbt import repo_root

    args = [sys.executable, str(repo_root() / "ops" / "sync_tenants.py")]
    if os.environ.get("DX_TENANTS_GIT_FETCH") == "1":
        args.append("--git-fetch")
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    context.log.info(proc.stdout[-2000:])
    if proc.returncode not in (0, 1):
        raise dg.Failure(description=proc.stderr[-1000:])
    return {"returncode": proc.returncode}


@dg.job(description="Đồng bộ sổ đăng ký khách mỗi 5 phút (FR-OPS-01)")
def sync_tenants() -> None:
    sync_tenants_op()


@dg.op
def healthcheck_cleanup_op(context: dg.OpExecutionContext) -> dict[str, Any]:
    from dx_pipelines.jobs.healthcheck import cleanup_expired

    res = cleanup_expired()
    context.log.info(str(res))
    return res


@dg.job(description="Xóa dữ liệu kiểm tra sức khỏe quá 14 ngày (FR-HC-04)")
def healthcheck_cleanup() -> None:
    healthcheck_cleanup_op()


@dg.op
def decision_reminders_op(context: dg.OpExecutionContext) -> dict[str, Any]:
    res = ApiClient().post("/v1/internal/decisions/remind")
    context.log.info(str(res))
    return res


@dg.job(description="Nhắc đo lại quyết định đến hạn (FR-DEC-02)")
def decision_reminders() -> None:
    decision_reminders_op()


@dg.op
def events_cleanup_op(context: dg.OpExecutionContext) -> dict[str, Any]:
    res = ApiClient().post("/v1/internal/events/cleanup", {"older_than_days": 90})
    context.log.info(str(res))
    return res


@dg.job(description="Xóa sự kiện đã xử lý cũ hơn 90 ngày")
def events_cleanup() -> None:
    events_cleanup_op()


TZ = "Asia/Ho_Chi_Minh"
SCHEDULES = [
    dg.ScheduleDefinition(job=fx_daily, cron_schedule="30 18 * * *", execution_timezone=TZ),
    dg.ScheduleDefinition(job=sync_tenants, cron_schedule="*/5 * * * *", execution_timezone=TZ),
    dg.ScheduleDefinition(job=healthcheck_cleanup, cron_schedule="0 3 * * *", execution_timezone=TZ),
    dg.ScheduleDefinition(job=decision_reminders, cron_schedule="0 8 * * *", execution_timezone=TZ),
    dg.ScheduleDefinition(job=events_cleanup, cron_schedule="0 4 * * *", execution_timezone=TZ),
]
