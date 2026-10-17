"""Hàm dùng chung của adapter file."""

from __future__ import annotations

import hashlib
from typing import Any

from connectors.files.readers import Row


def buyer_hash(salt: str, value: Any) -> str | None:
    """Băm mã người mua ngay khi đọc (NFR-03); giá trị gốc không đi tiếp."""
    if value in (None, ""):
        return None
    return hashlib.sha256(f"{salt}|{str(value).strip().lower()}".encode()).hexdigest()


def rows(data: list[dict[str, Any]]) -> list[Row]:
    return [Row(d) for d in data]


def order_record(
    order_id: str,
    ordered_at: Any,
    status_raw: Any,
    *,
    seller_discount: Any = 0,
    platform_discount: Any = 0,
    buyer_ref_hash: str | None = None,
    currency: str = "VND",
) -> dict[str, Any]:
    return {
        "order_id": order_id,
        "ordered_at": ordered_at,
        "status_raw": status_raw,
        "currency": currency,
        "order_seller_discount": seller_discount or 0,
        "order_platform_discount": platform_discount or 0,
        "buyer_ref_hash": buyer_ref_hash,
    }


def line_record(
    line_id: str,
    order_id: str,
    sku: Any,
    name: Any,
    qty: Any,
    unit_original: Any,
    seller_discount: Any = 0,
    platform_discount: Any = 0,
) -> dict[str, Any]:
    return {
        "line_id": line_id,
        "order_id": order_id,
        "seller_sku": sku,
        "item_name": name,
        "quantity": qty,
        "unit_original_price": unit_original,
        "line_seller_discount": seller_discount or 0,
        "line_platform_discount": platform_discount or 0,
    }


def return_record(line_id: str, order_id: str, returned_at: Any, refund: Any, fee: Any = 0) -> dict[str, Any]:
    """Hoàn tiền theo dòng đơn trong file xuất đơn (cột "Số tiền hoàn lại", "Refund Amount"...)."""
    return {
        "return_id": f"R-{line_id}",
        "order_id": order_id,
        "line_id": line_id,
        "returned_at": returned_at,
        "refund_amount": refund,
        "return_fee": fee or 0,
    }


def fee_record(order_id: str, fee_date: Any, fee_type: str, amount: Any, suffix: str = "") -> dict[str, Any]:
    return {
        "fee_id": f"{order_id}-{fee_type}{suffix}",
        "order_id": order_id,
        "fee_date": fee_date,
        "fee_type_raw": fee_type,
        "amount": amount,
        "currency": "VND",
    }
