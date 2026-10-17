"""Mẫu giá vốn DataxLand (spec 05 §6.4) cho lượt kiểm tra sức khỏe."""

from __future__ import annotations

from typing import Any

from connectors.files.adapters.common import rows
from connectors.files.readers import to_date, to_num, to_text


def costs(data: list[dict[str, Any]], salt: str) -> dict[str, list[dict[str, Any]]]:
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows(data), start=1):
        sku = to_text(r.get("ma_sku", "Mã SKU", "SKU"))
        cost = to_num(r.get("gia_von", "Giá vốn"))
        if not sku or cost is None or cost < 0:
            continue
        out.append(
            {
                "id": f"file-{i}",
                "seller_sku": sku,
                "unit_cost_vnd": cost,
                "valid_from": to_date(r.get("ap_dung_tu", "Áp dụng từ")) or to_date("2000-01-01"),
                "note": to_text(r.get("ghi_chu", "Ghi chú")),
            }
        )
    return {"portal_file__product_costs": out}
