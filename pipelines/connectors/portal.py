"""Nguồn `portal`: giá vốn và ngân sách khách nhập trên cổng (spec 01 §7).

Đọc bảng `product_costs`, `ad_budgets` của khách trong Postgres (lọc `tenant_id`), ghi ảnh chụp đầy đủ vào
`<prefix>_raw.portal__product_costs` và `portal__ad_budgets`, kể cả bản ghi đã xóa mềm (`deleted_at`) để raw
nhận được trạng thái xóa. Chạy ở đầu mỗi lần chạy pipeline của khách.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from connectors.base import SyncContext, SyncOutcome, with_contract
from dx_common.db import get_engine
from dx_common.tenants import SourceConfig, TenantConfig

COST_COLUMNS = {
    "id": "string",
    "tenant_id": "string",
    "seller_sku": "string",
    "unit_cost_vnd": "string",
    "valid_from": "date",
    "note": "string",
    "deleted_at": "timestamp",
    "created_at": "timestamp",
    "updated_at": "timestamp",
    "_dx_loaded_at": "timestamp",
    "_dx_source_account": "string",
    "_dx_record_hash": "string",
}
BUDGET_COLUMNS = {
    "id": "string",
    "tenant_id": "string",
    "platform": "string",
    "month": "date",
    "budget_vnd": "string",
    "deleted_at": "timestamp",
    "created_at": "timestamp",
    "updated_at": "timestamp",
    "_dx_loaded_at": "timestamp",
    "_dx_source_account": "string",
    "_dx_record_hash": "string",
}


def _rows(sql: str, tenant_id: str) -> list[dict[str, Any]]:
    with get_engine().connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(sql), {"t": tenant_id})]


def sync_portal(tenant: TenantConfig, source: SourceConfig, ctx: SyncContext) -> SyncOutcome:
    costs = _rows(
        "select id, tenant_id, seller_sku, unit_cost_vnd::text as unit_cost_vnd, valid_from, note, deleted_at,"
        " created_at, updated_at from product_costs where tenant_id = :t order by id",
        tenant.tenant_id,
    )
    budgets = _rows(
        "select id, tenant_id, platform, month, budget_vnd::text as budget_vnd, deleted_at, created_at, updated_at"
        " from ad_budgets where tenant_id = :t order by id",
        tenant.tenant_id,
    )
    n1 = ctx.warehouse.write_rows(
        ctx.raw_dataset, "portal__product_costs", COST_COLUMNS, [with_contract(r, "portal", ctx.now) for r in costs]
    )
    n2 = ctx.warehouse.write_rows(
        ctx.raw_dataset, "portal__ad_budgets", BUDGET_COLUMNS, [with_contract(r, "portal", ctx.now) for r in budgets]
    )
    return SyncOutcome(rows_loaded=n1 + n2, tables={"portal__product_costs": n1, "portal__ad_budgets": n2})
