"""Job `weekly_report` (FR-REP-01, spec 04 §3.3, spec 06 §4.2).

Chờ tối đa 3 giờ cho một lần `tenant_pipeline` thành công bắt đầu sau (thời điểm đến hạn − chu kỳ đồng bộ);
không có thì dựng báo cáo từ lần chạy tốt gần nhất và đánh dấu `data_stale = true`.
"""

import time
from datetime import datetime, timedelta
from typing import Any

import dagster as dg

from dx_common.timeutil import iso_z, now_utc
from dx_pipelines.api_client import ApiClient
from dx_pipelines.partitions import tenants_partitions
from dx_pipelines.resources import load_tenant
from dx_pipelines.schedule import sync_interval

WAIT_MAX = timedelta(hours=3)
POLL = 300


class WeeklyReportConfig(dg.Config):
    due_at: str = ""  # ISO, giờ đến hạn; trống = bây giờ
    wait: bool = True


def wait_for_good_run(
    api: ApiClient, tenant_id: str, since: datetime, deadline: datetime, sleep: Any = time.sleep
) -> dict[str, Any] | None:
    while True:
        r = api.post("/v1/internal/runs/latest", {"tenant_id": tenant_id, "status": "success", "since": iso_z(since)})
        if r.get("run_id"):
            return r
        if now_utc() >= deadline:
            return None
        sleep(POLL)


@dg.op
def build_weekly_report(context: dg.OpExecutionContext, config: WeeklyReportConfig) -> dict[str, Any]:
    tenant_id = context.partition_key
    tenant = load_tenant(tenant_id)
    api = ApiClient()
    due = datetime.fromisoformat(config.due_at) if config.due_at else now_utc()
    since = due - sync_interval(tenant.schedule.sync or "0 */6 * * *", due)
    good = wait_for_good_run(api, tenant_id, since, now_utc() + (WAIT_MAX if config.wait else timedelta(0)))
    stale = good is None
    if stale:
        context.log.warning("Không có lần chạy tốt mới; dựng từ lần chạy tốt gần nhất (data_stale)")
        good = api.post("/v1/internal/runs/latest", {"tenant_id": tenant_id, "status": "success"})
    res = api.build_report(tenant_id, None, (good or {}).get("run_id"), stale)
    context.log.info(f"Báo cáo {res.get('report_id')} ({res.get('status')})")
    return res


@dg.job(partitions_def=tenants_partitions, description="Dựng bản nháp báo cáo tuần cho khách")
def weekly_report() -> None:
    build_weekly_report()
