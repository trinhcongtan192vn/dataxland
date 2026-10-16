"""Bảng raw của Shopee (spec 01 §3). Mỗi hàm trả bản ghi phẳng đúng cột dữ liệu mẫu trong `transform/samples/shopee`.

| Bảng | Đường lấy |
|---|---|
| `shopee__orders`, `shopee__order_items` | `get_order_list` theo `update_time` (cửa sổ 7 ngày) + đơn mở cần quét lại → `get_order_detail` (50 đơn/lần); phần voucher và phí ship người mua trả lấy từ `get_escrow_detail` |
| `shopee__escrow` | `get_escrow_detail` cho đơn `COMPLETED` |
| `shopee__returns` | `get_return_list` theo `update_time` |
| `shopee__products` | `get_item_list` → `get_item_base_info` → `get_model_list` |
| `shopee__daily_totals` | Đếm `get_order_list` theo `create_time` theo ngày (không gọi chi tiết); `gross_amount` để trống vì API danh sách không trả tiền |
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

from connectors.common.load import cursor_start, windows
from connectors.shopee.client import ShopeeClient
from dx_common.timeutil import VN_TZ

FINAL = {"COMPLETED", "CANCELLED"}
DETAIL_FIELDS = (
    "buyer_user_id,buyer_username,estimated_shipping_fee,recipient_address,item_list,pay_time,total_amount,"
    "actual_shipping_fee"
)
WINDOW_DAYS = 7  # Shopee giới hạn khoảng thời gian của get_order_list ≤ 15 ngày


def _epoch(d: datetime) -> int:
    return int(d.timestamp())


def list_orders(c: ShopeeClient, field: str, start: datetime, end: datetime) -> Iterator[dict[str, Any]]:
    for a, b in windows(start, end, WINDOW_DAYS):
        cursor = ""
        while True:
            r = c.get(
                "/api/v2/order/get_order_list",
                time_range_field=field,
                time_from=_epoch(a),
                time_to=_epoch(b),
                page_size=100,
                cursor=cursor,
                response_optional_fields="order_status",
            )
            yield from r.get("order_list") or []
            if not r.get("more"):
                break
            cursor = str(r.get("next_cursor") or "")


class OrderFetcher:
    """Lấy chi tiết + escrow một lần, chia cho ba bảng orders, order_items, escrow."""

    def __init__(self, c: ShopeeClient, now: datetime, rescan: list[str]) -> None:
        self.c, self.now, self.rescan = c, now, rescan
        self._orders: list[dict[str, Any]] | None = None
        self._items: list[dict[str, Any]] = []
        self._escrow: list[dict[str, Any]] = []

    def _load(self, state: dict[str, Any]) -> None:
        if self._orders is not None:
            return
        start, _ = cursor_start(state, "orders_cursor", self.now)
        sns = [o["order_sn"] for o in list_orders(self.c, "update_time", start, self.now)]
        sns = list(dict.fromkeys([*sns, *self.rescan]))
        orders: list[dict[str, Any]] = []
        max_upd = int(state.get("orders_cursor") or 0)
        for i in range(0, len(sns), 50):
            r = self.c.get(
                "/api/v2/order/get_order_detail",
                order_sn_list=",".join(sns[i : i + 50]),
                response_optional_fields=DETAIL_FIELDS,
            )
            for d in r.get("order_list") or []:
                orders.append(self._order(d))
                max_upd = max(max_upd, int(d.get("update_time") or 0))
        self._orders = orders
        state["orders_cursor"] = max_upd or _epoch(self.now)

    def _order(self, d: dict[str, Any]) -> dict[str, Any]:
        items = d.get("item_list") or []
        orig = sum(int(i.get("model_original_price") or 0) * int(i.get("model_quantity_purchased") or 0) for i in items)
        disc = sum(
            int(i.get("model_discounted_price") or 0) * int(i.get("model_quantity_purchased") or 0) for i in items
        )
        status = str(d.get("order_status") or "")
        inc: dict[str, Any] = {}
        if status not in ("UNPAID", "CANCELLED", "IN_CANCEL"):
            inc = self.c.get("/api/v2/payment/get_escrow_detail", order_sn=d["order_sn"]).get("order_income") or {}
        if status == "COMPLETED" and inc:
            self._escrow.append(
                {
                    "order_sn": d["order_sn"],
                    "escrow_amount": inc.get("escrow_amount"),
                    "buyer_total_amount": inc.get("buyer_total_amount"),
                    "original_price": inc.get("original_price"),
                    "seller_discount": inc.get("seller_discount"),
                    "voucher_from_seller": inc.get("voucher_from_seller"),
                    "voucher_from_shopee": inc.get("voucher_from_shopee"),
                    "commission_fee": inc.get("commission_fee"),
                    "service_fee": inc.get("service_fee"),
                    "seller_transaction_fee": inc.get("seller_transaction_fee"),
                    "actual_shipping_fee": inc.get("actual_shipping_fee"),
                    "shopee_shipping_rebate": inc.get("shopee_shipping_rebate"),
                    "buyer_paid_shipping_fee": inc.get("buyer_paid_shipping_fee"),
                    "reverse_shipping_fee": inc.get("reverse_shipping_fee"),
                    # get_escrow_detail không trả thời điểm quyết toán; dùng update_time của đơn đã hoàn tất.
                    "escrow_release_time": inc.get("escrow_release_time") or d.get("update_time"),
                }
            )
        for i in items:
            self._items.append(
                {
                    "order_sn": d["order_sn"],
                    "item_id": i.get("item_id"),
                    "item_name": i.get("item_name"),
                    "item_sku": i.get("item_sku"),
                    "model_id": i.get("model_id"),
                    "model_sku": i.get("model_sku"),
                    "model_quantity_purchased": i.get("model_quantity_purchased"),
                    "model_original_price": i.get("model_original_price"),
                    "model_discounted_price": i.get("model_discounted_price"),
                }
            )
        addr = d.get("recipient_address") or {}
        return {
            "order_sn": d["order_sn"],
            "order_status": status,
            "create_time": d.get("create_time"),
            "update_time": d.get("update_time"),
            "pay_time": d.get("pay_time"),
            "currency": d.get("currency") or "VND",
            "total_amount": d.get("total_amount"),
            "order_original_amount": orig,
            "order_discounted_amount": disc,
            "seller_voucher": inc.get("voucher_from_seller", 0),
            "shopee_voucher": inc.get("voucher_from_shopee", 0),
            "buyer_paid_shipping_fee": inc.get("buyer_paid_shipping_fee"),
            "estimated_shipping_fee": d.get("estimated_shipping_fee"),
            "buyer_user_id": d.get("buyer_user_id"),
            "buyer_username": d.get("buyer_username"),
            "recipient_name": addr.get("name"),
            "recipient_phone": addr.get("phone"),
            "recipient_full_address": addr.get("full_address"),
        }

    def orders(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        self._load(state)
        return list(self._orders or [])

    def items(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        self._load(state)
        return self._items

    def escrow(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        self._load(state)
        return self._escrow


def returns(c: ShopeeClient, now: datetime, state: dict[str, Any]) -> Iterator[dict[str, Any]]:
    start, _ = cursor_start(state, "returns_cursor", now)
    max_upd = int(state.get("returns_cursor") or 0)
    for a, b in windows(start, now, 14):
        page = 0
        while True:
            r = c.get(
                "/api/v2/returns/get_return_list",
                page_no=page,
                page_size=100,
                update_time_from=_epoch(a),
                update_time_to=_epoch(b),
            )
            for x in r.get("return") or []:
                item = (x.get("item") or [{}])[0]
                max_upd = max(max_upd, int(x.get("update_time") or 0))
                yield {
                    "return_sn": x.get("return_sn"),
                    "order_sn": x.get("order_sn"),
                    "status": x.get("status"),
                    "reason": x.get("reason"),
                    "refund_amount": x.get("refund_amount"),
                    "return_ship_fee": (
                        x.get("return_ship_fee")
                        if x.get("return_ship_fee") is not None
                        else (x.get("logistics_fee") or {}).get("return_ship_fee")
                    ),
                    "item_id": item.get("item_id"),
                    "model_id": item.get("model_id"),
                    "item_sku": item.get("item_sku") or item.get("variation_sku"),
                    "create_time": x.get("create_time"),
                    "update_time": x.get("update_time"),
                }
            if not r.get("more"):
                break
            page += 1
    state["returns_cursor"] = max_upd or _epoch(now)


def products(c: ShopeeClient) -> Iterator[dict[str, Any]]:
    offset = 0
    ids: list[int] = []
    while True:
        r = c.get("/api/v2/product/get_item_list", offset=offset, page_size=100, item_status="NORMAL")
        ids += [int(i["item_id"]) for i in r.get("item") or []]
        if not r.get("has_next_page"):
            break
        offset = int(r.get("next_offset") or offset + 100)
    for i in range(0, len(ids), 50):
        info = c.get("/api/v2/product/get_item_base_info", item_id_list=",".join(str(x) for x in ids[i : i + 50]))
        for it in info.get("item_list") or []:
            base = {
                "item_id": it.get("item_id"),
                "item_name": it.get("item_name"),
                "item_sku": it.get("item_sku"),
                "category_id": it.get("category_id"),
                "category_name": None,
                "gtin_code": it.get("gtin_code"),
            }
            if not it.get("has_model"):
                yield {**base, "model_id": 0, "model_name": "Mặc định", "model_sku": it.get("item_sku")}
                continue
            models = c.get("/api/v2/product/get_model_list", item_id=it["item_id"])
            for m in models.get("model") or []:
                yield {
                    **base,
                    "model_id": m.get("model_id"),
                    "model_name": m.get("model_name"),
                    "model_sku": m.get("model_sku"),
                    "gtin_code": m.get("gtin_code") or base["gtin_code"],
                }


def daily_totals(c: ShopeeClient, now: datetime, state: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Đếm đơn theo ngày tạo (giờ Việt Nam) cho các ngày từ con trỏ (hoặc 90 ngày) tới hôm qua, luôn lấy lại 30 ngày."""
    today = now.astimezone(VN_TZ).date()
    last = state.get("totals_last_date")
    first = (
        today - timedelta(days=90)
        if last is None
        else min(datetime.fromisoformat(str(last)).date() + timedelta(days=1), today - timedelta(days=30))
    )
    d = first
    while d < today:
        start = datetime(d.year, d.month, d.day, tzinfo=VN_TZ)
        n = sum(1 for _ in list_orders(c, "create_time", start, start + timedelta(days=1)))
        yield {"date": d.isoformat(), "order_count": n, "gross_amount": None, "currency": "VND"}
        d += timedelta(days=1)
    state["totals_last_date"] = (today - timedelta(days=1)).isoformat()
