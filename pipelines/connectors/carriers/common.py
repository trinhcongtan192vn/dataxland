"""Phần dùng chung của connector hãng vận chuyển (spec 01 §9, FR-ING-09, ADR 0005).

Bảng raw `<hãng>__shipments` (khóa mã vận đơn): phí vận chuyển, COD, trạng thái, phí hoàn. Không có thông tin người
nhận. GHN và GHTK không có API liệt kê đơn của shop: mã vận đơn đến từ webhook (`carrier_events` trong Postgres),
connector gọi API chi tiết cho vận đơn chưa ở trạng thái cuối để lấy phí và COD.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from dx_common.db import get_engine
from dx_common.secrets import get_secret_store

SHIPMENTS = {
    "waybill": "string",
    "client_order_code": "string",
    "status_raw": "string",
    "created_at": "timestamp",
    "updated_at": "timestamp",
    "shipping_fee": "numeric",
    "cod_amount": "numeric",
    "return_fee": "numeric",
    "insurance_fee": "numeric",
    "weight_g": "int",
}
REFRESH_DAYS = 60


def credentials(secret_ref: str) -> dict[str, Any]:
    """Secret dạng JSON: GHN `{"token", "shop_id"}`, GHTK `{"token", "partner_code"}`."""
    return dict(json.loads(get_secret_store().get(secret_ref)))


def latest_events(tenant_id: str, carrier: str, since: datetime) -> dict[str, dict[str, Any]]:
    """Trạng thái mới nhất của mỗi vận đơn có sự kiện trong `REFRESH_DAYS` ngày, cùng thời điểm tạo (sự kiện đầu)."""
    sql = text(
        "select waybill, client_order_code, status_raw, event_at, shipping_fee, cod_amount, "
        "min(event_at) over (partition by waybill) as first_at, "
        "row_number() over (partition by waybill order by event_at desc, created_at desc) as rn "
        "from carrier_events where tenant_id = :t and carrier = :c and event_at >= :since"
    )
    out: dict[str, dict[str, Any]] = {}
    with get_engine().connect() as conn:
        for r in conn.execute(sql, {"t": tenant_id, "c": carrier, "since": since}).mappings():
            if r["rn"] == 1:
                out[str(r["waybill"])] = dict(r)
    return out


def shipment_rows(
    events: dict[str, dict[str, Any]],
    final: set[str],
    fetch: Callable[[str], dict[str, Any] | None] | None,
) -> list[dict[str, Any]]:
    """Một dòng mỗi vận đơn: từ sự kiện webhook, bổ sung bằng API chi tiết khi vận đơn chưa ở trạng thái cuối."""
    rows: list[dict[str, Any]] = []
    for waybill, ev in sorted(events.items()):
        row: dict[str, Any] = {
            "waybill": waybill,
            "client_order_code": ev.get("client_order_code"),
            "status_raw": str(ev["status_raw"]),
            "created_at": ev.get("first_at") or ev["event_at"],
            "updated_at": ev["event_at"],
            "shipping_fee": ev.get("shipping_fee"),
            "cod_amount": ev.get("cod_amount"),
            "return_fee": None,
            "insurance_fee": None,
            "weight_g": None,
        }
        if fetch is not None and str(ev["status_raw"]).lower() not in final:
            detail = fetch(waybill)
            if detail:
                row.update({k: v for k, v in detail.items() if v is not None})
        rows.append(row)
    return rows


def since(now: datetime) -> datetime:
    return now - timedelta(days=REFRESH_DAYS)


def dec(v: Any) -> Decimal | None:
    if v in (None, ""):
        return None
    return Decimal(str(v))
