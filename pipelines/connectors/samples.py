"""Adapter dữ liệu mẫu cho môi trường `local` (spec 00 §4, §5).

Ở `local`, dữ liệu sàn được nạp bằng `make seed-local`; adapter này chỉ kiểm tra bảng raw đã có và báo số dòng,
không gọi API thật. Chỉ được chọn khi `DX_ENV=local` và nguồn chưa có secret (xem `connectors.registry`).
"""

from __future__ import annotations

from connectors.base import SourceError, SyncContext, SyncOutcome
from dx_common.tenants import SourceConfig, TenantConfig


def sync_from_samples(tenant: TenantConfig, source: SourceConfig, ctx: SyncContext) -> SyncOutcome:
    tables = [t for t in ctx.warehouse.list_tables(ctx.raw_dataset) if t.startswith(f"{source.type}__")]
    if not tables:
        raise SourceError("api_error", f"chưa có dữ liệu mẫu cho {source.type}; chạy `make seed-local`")
    return SyncOutcome(
        rows_loaded=0, status="skipped", tables={t: 0 for t in tables}, note="local: dùng dữ liệu mẫu đã nạp"
    )
