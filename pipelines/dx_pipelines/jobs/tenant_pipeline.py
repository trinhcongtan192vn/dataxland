"""Job `tenant_pipeline` (FR-OPS-03, spec 04 §3.2). Các bước nằm trong `dx_pipelines.runner`."""

from typing import Any

import dagster as dg

from dx_pipelines.partitions import tenants_partitions
from dx_pipelines.resources import load_tenant, services_for
from dx_pipelines.runner import TenantPipeline


class TenantRunConfig(dg.Config):
    history: bool = False  # lần chạy đầu: nạp lịch sử 90 ngày (FR-ING-05)
    full_refresh: bool = False  # xóa dữ liệu người mua cần dbt --full-refresh (spec 04 §8)
    select: list[str] = []


@dg.op(tags={"kind": "dx"})
def run_tenant_pipeline(context: dg.OpExecutionContext, config: TenantRunConfig) -> dict[str, Any]:
    tenant_id = context.partition_key
    tenant = load_tenant(tenant_id)
    pipe = TenantPipeline(
        tenant,
        context.run_id,
        services_for(tenant_id),
        history=config.history,
        full_refresh=config.full_refresh,
        select=config.select or None,
    )
    out = pipe.run()
    for step, status in out.steps.items():
        context.log.info(f"{step}: {status}")
    for w in out.warnings:
        context.log.warning(w)
    result = {"status": out.status, "failed_step": out.failed_step, "steps": out.steps}
    if out.status == "failed":
        raise dg.Failure(description=f"Bước {out.failed_step} lỗi", metadata=result)
    if out.status == "blocked":
        raise dg.Failure(description="Có test chặn; marts, Cube và báo cáo được giữ nguyên", metadata=result)
    return result


@dg.job(partitions_def=tenants_partitions, description="Đồng bộ → dbt → test → hoán đổi marts → Cube → bất thường")
def tenant_pipeline() -> None:
    run_tenant_pipeline()
