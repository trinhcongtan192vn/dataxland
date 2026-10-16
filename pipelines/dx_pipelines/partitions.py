"""Partition động `tenants`: mỗi khách là một partition (spec 04 §3.1)."""

from __future__ import annotations

import dagster as dg

tenants_partitions = dg.DynamicPartitionsDefinition(name="tenants")


def tenant_tags(tenant_id: str) -> dict[str, str]:
    # Giới hạn mỗi khách một lần chạy cùng lúc qua tag này (pipelines/dagster.yaml).
    return {"dx/tenant": tenant_id}
