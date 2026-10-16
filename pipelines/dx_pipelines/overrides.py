"""Nạp file ghi đè ánh xạ trạng thái của khách vào `<prefix>_raw.dx__status_map_override` (spec 02 §3.3, 04 §3.2).

Bảng luôn được tạo (có thể trống) để staging nối được. File sai cột hoặc trạng thái ngoài bộ chuẩn → lỗi
`override_invalid`.
"""

from __future__ import annotations

import csv
from pathlib import Path

from dx_common.tenants import TenantConfig

STANDARD_STATUSES = frozenset(
    {"pending", "confirmed", "shipping", "delivered", "completed", "cancelled", "returned", "failed_delivery"}
)
COLUMNS = {"source": "string", "status_raw": "string", "status": "string"}


class OverrideInvalid(ValueError):
    pass


def read_overrides(tenant: TenantConfig, repo_root: Path) -> list[dict[str, str]]:
    rel = tenant.overrides.status_map
    if not rel:
        return []
    p = (repo_root / rel).resolve()
    if not p.is_file() or repo_root.resolve() not in p.parents:
        raise OverrideInvalid(f"không tìm thấy file ghi đè {rel}")
    with p.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if set(reader.fieldnames or []) != {"source", "status_raw", "status"}:
            raise OverrideInvalid("file ghi đè phải có đúng cột source,status_raw,status")
        rows = [{k: (v or "").strip() for k, v in r.items()} for r in reader]
    bad = [r for r in rows if r["status"] not in STANDARD_STATUSES or not r["source"] or not r["status_raw"]]
    if bad:
        raise OverrideInvalid(f"dòng ghi đè không hợp lệ: {bad[0]}")
    return rows


def load_overrides(tenant: TenantConfig, repo_root: Path, warehouse: object, raw_dataset: str) -> int:
    rows = read_overrides(tenant, repo_root)
    warehouse.ensure_dataset(raw_dataset, {"tenant_id": tenant.tenant_id})  # type: ignore[attr-defined]
    return int(warehouse.write_rows(raw_dataset, "dx__status_map_override", COLUMNS, rows))  # type: ignore[attr-defined]
