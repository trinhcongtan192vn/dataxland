"""Bảng raw của TikTok Shop (spec 01 §4). Bản ghi phẳng đúng cột dữ liệu mẫu trong `transform/samples/tiktok_shop`.

| Bảng | Đường lấy |
|---|---|
| `tiktok_shop__orders`, `tiktok_shop__order_items` | `POST /order/202309/orders/search` theo `update_time` (cửa sổ 7 ngày) + đơn mở cần quét lại → `GET /order/202309/orders?ids=` |
| `tiktok_shop__settlements` | `GET /finance/202309/orders/{order_id}/statement_transactions` cho đơn `COMPLETED` |
| `tiktok_shop__returns` | `POST /return_refund/202309/returns/search` theo `update_time` |
| `tiktok_shop__products` | `POST /product/202309/products/search` → `GET /product/202309/products/{id}` |
| `tiktok_shop__daily_totals` | `orders/search` theo `create_time` theo ngày, chỉ đọc tổng của danh sách (không gọi chi tiết) |
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

from connectors.common.load import cursor_start, windows
from connectors.tiktok_shop.client import TikTokClient
from dx_common.timeutil import VN_TZ

FINAL = {"COMPLETED", "CANCELLED"}


def _epoch(d: datetime) -> int:
    return int(d.timestamp())


def search_orders(c: TikTokClient, field: str, start: datetime, end: datetime) -> Iterator[dict[str, Any]]:
    for a, b in windows(start, end):
        token = ""
        while True:
            params: dict[str, Any] = {"page_size": 100, "sort_field": field}
            if token:
                params["page_token"] = token
            r = c.call(
                "POST", "/order/202309/orders/search", params, {f"{field}_ge": _epoch(a), f"{field}_lt": _epoch(b)}
            )
            yield from r.get("orders") or []
            token = str(r.get("next_page_token") or "")
            if not token:
                break


def _num(v: Any) -> Any:
    return None if v in (None, "") else v


class OrderFetcher:
    def __init__(self, c: TikTokClient, now: datetime, rescan: list[str]) -> None:
        self.c, self.now, self.rescan = c, now, rescan
        self._orders: list[dict[str, Any]] | None = None
        self._items: list[dict[str, Any]] = []
        self._settlements: list[dict[str, Any]] = []

    def _load(self, state: dict[str, Any]) -> None:
        if self._orders is not None:
            return
        start, _ = cursor_start(state, "orders_cursor", self.now)
        found = {o["id"]: o for o in search_orders(self.c, "update_time", start, self.now)}
        missing = [i for i in self.rescan if i not in found]
        for i in range(0, len(missing), 50):
            r = self.c.call("GET", "/order/202309/orders", {"ids": ",".join(missing[i : i + 50])})
            for o in r.get("orders") or []:
                found[o["id"]] = o
        max_upd = int(state.get("orders_cursor") or 0)
        self._orders = []
        for o in found.values():
            max_upd = max(max_upd, int(o.get("update_time") or 0))
            self._orders.append(self._order(o))
        state["orders_cursor"] = max_upd or _epoch(self.now)

    def _order(self, o: dict[str, Any]) -> dict[str, Any]:
        pay = o.get("payment") or {}
        addr = o.get("recipient_address") or {}
        status = str(o.get("status") or "")
        for li in o.get("line_items") or []:
            self._items.append(
                {
                    "id": li.get("id"),
                    "order_id": o["id"],
                    "product_id": li.get("product_id"),
                    "product_name": li.get("product_name"),
                    "sku_id": li.get("sku_id"),
                    "sku_name": li.get("sku_name"),
                    "seller_sku": li.get("seller_sku"),
                    "quantity": li.get("quantity", 1),
                    "original_price": _num(li.get("original_price")),
                    "sale_price": _num(li.get("sale_price")),
                    "platform_discount": _num(li.get("platform_discount")),
                    "seller_discount": _num(li.get("seller_discount")),
                }
            )
        if status == "COMPLETED":
            st = self.c.call("GET", f"/finance/202309/orders/{o['id']}/statement_transactions")
            for t in st.get("statement_transactions") or []:
                self._settlements.append(
                    {
                        "order_id": o["id"],
                        "transaction_id": t.get("id"),
                        "statement_time": t.get("statement_time"),
                        "currency": st.get("currency") or t.get("currency") or pay.get("currency"),
                        "revenue_amount": _num(t.get("revenue_amount")),
                        "settlement_amount": _num(t.get("settlement_amount")),
                        "shipping_cost_amount": _num(t.get("shipping_cost_amount")),
                        "platform_commission_amount": _num(t.get("platform_commission_amount")),
                        "transaction_fee_amount": _num(t.get("transaction_fee_amount")),
                        "affiliate_commission_amount": _num(t.get("affiliate_commission_amount")),
                    }
                )
        return {
            "id": o["id"],
            "status": status,
            "create_time": o.get("create_time"),
            "update_time": o.get("update_time"),
            "paid_time": o.get("paid_time"),
            "user_id": o.get("user_id"),
            "buyer_email": o.get("buyer_email"),
            "currency": pay.get("currency") or "VND",
            "original_total_product_price": _num(pay.get("original_total_product_price")),
            "platform_discount": _num(pay.get("platform_discount")),
            "seller_discount": _num(pay.get("seller_discount")),
            "shipping_fee": _num(pay.get("shipping_fee")),
            "sub_total": _num(pay.get("sub_total")),
            "total_amount": _num(pay.get("total_amount")),
            "recipient_name": addr.get("name"),
            "recipient_phone_number": addr.get("phone_number"),
            "recipient_full_address": addr.get("full_address"),
        }

    def orders(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        self._load(state)
        return list(self._orders or [])

    def items(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        self._load(state)
        return self._items

    def settlements(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        self._load(state)
        return self._settlements


def returns(c: TikTokClient, now: datetime, state: dict[str, Any]) -> Iterator[dict[str, Any]]:
    start, _ = cursor_start(state, "returns_cursor", now)
    max_upd = int(state.get("returns_cursor") or 0)
    for a, b in windows(start, now):
        token = ""
        while True:
            params: dict[str, Any] = {"page_size": 50}
            if token:
                params["page_token"] = token
            r = c.call(
                "POST",
                "/return_refund/202309/returns/search",
                params,
                {"update_time_ge": _epoch(a), "update_time_lt": _epoch(b)},
            )
            for x in r.get("return_orders") or []:
                ref = x.get("refund_amount") or {}
                line = (x.get("return_line_items") or [{}])[0]
                max_upd = max(max_upd, int(x.get("update_time") or 0))
                yield {
                    "return_id": x.get("return_id"),
                    "order_id": x.get("order_id"),
                    "line_item_id": line.get("order_line_item_id"),
                    "return_type": x.get("return_type"),
                    "return_status": x.get("return_status"),
                    "return_reason": x.get("return_reason"),
                    "refund_total": _num(ref.get("refund_total")),
                    "return_shipping_fee": _num(ref.get("return_shipping_fee") or x.get("return_shipping_fee")),
                    "create_time": x.get("create_time"),
                    "update_time": x.get("update_time"),
                }
            token = str(r.get("next_page_token") or "")
            if not token:
                break
    state["returns_cursor"] = max_upd or _epoch(now)


def products(c: TikTokClient) -> Iterator[dict[str, Any]]:
    token = ""
    ids: list[str] = []
    while True:
        params: dict[str, Any] = {"page_size": 100}
        if token:
            params["page_token"] = token
        r = c.call("POST", "/product/202309/products/search", params, {"status": "ACTIVATE"})
        ids += [str(p["id"]) for p in r.get("products") or []]
        token = str(r.get("next_page_token") or "")
        if not token:
            break
    for pid in ids:
        p = c.call("GET", f"/product/202309/products/{pid}")
        chain = p.get("category_chains") or []
        cat = chain[-1].get("local_name") if chain else None
        for s in p.get("skus") or []:
            ident = s.get("identifier_code") or {}
            yield {
                "product_id": pid,
                "title": p.get("title"),
                "category_name": cat,
                "sku_id": s.get("id"),
                "seller_sku": s.get("seller_sku"),
                "sku_name": ", ".join(a.get("value_name", "") for a in s.get("sales_attributes") or []) or "Mặc định",
                "barcode": ident.get("code"),
            }


def daily_totals(c: TikTokClient, now: datetime, state: dict[str, Any]) -> Iterator[dict[str, Any]]:
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
        n, gross, cur = 0, 0, "VND"
        for o in search_orders(c, "create_time", start, start + timedelta(days=1)):
            pay = o.get("payment") or {}
            n += 1
            gross += int(float(pay.get("original_total_product_price") or 0))
            cur = pay.get("currency") or cur
        yield {"date": d.isoformat(), "order_count": n, "gross_amount": gross, "currency": cur}
        d += timedelta(days=1)
    state["totals_last_date"] = (today - timedelta(days=1)).isoformat()
