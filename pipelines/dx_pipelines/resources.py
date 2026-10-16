"""Tài nguyên dùng chung cho job (spec 04 §3.1): API nội bộ, kho dữ liệu theo khách, dbt, Cube."""

from __future__ import annotations

from typing import Any

from dx_common.tenants import TenantConfig
from dx_pipelines.api_client import ApiClient
from dx_pipelines.cube import CubeAdmin
from dx_pipelines.dbt import DbtProject
from dx_pipelines.runner import Services
from dx_pipelines.warehouse import get_warehouse


def services_for(tenant_id: str) -> Services:
    """Mỗi lần chạy dùng tài khoản dịch vụ của khách (impersonation), không dùng tài khoản của Dagster."""
    return Services(api=ApiClient(), warehouse=get_warehouse(tenant_id), dbt=DbtProject(), cube=CubeAdmin())


def load_tenant(tenant_id: str) -> TenantConfig:
    for t in ApiClient().tenants():
        if t["tenant_id"] == tenant_id:
            return TenantConfig.model_validate(t["config"])
    raise KeyError(f"không có khách {tenant_id} trong sổ đăng ký")


def active_tenants() -> list[dict[str, Any]]:
    return ApiClient().tenants(["active", "trial"])
