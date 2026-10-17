"""Bảng raw của Lazada (spec 01 §5). Bản ghi phẳng đúng cột dữ liệu mẫu trong `transform/samples/lazada`.

| Bảng | Endpoint |
|---|---|
| `lazada__orders` | `/orders/get` theo `update_after`/`update_before` (cửa sổ 7 ngày) + đơn mở cần quét lại qua `/order/get` |
| `lazada__order_items` | `/orders/items/get` (tối đa 50 đơn mỗi lần) |
| `lazada__transactions` | `/finance/transaction/details/get` theo ngày giao dịch |
| `lazada__returns` | `/reverse/getreverseordersforseller` |
| `lazada__products` | `/products/get` |
| `lazada__daily_totals` | `/orders/get` theo `created_after`/`created_before` từng ngày, cộng `price` từ danh sách |
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

from connectors.common.load import cursor_start, windows
from connectors.lazada.client import LazadaClient
from dx_common.timeutil import VN_TZ

FINAL = {"DELIVERED", "CONFIRMED", "CANCELED", "RETURNED", "SHIPPED_BACK", "FAILED_DELIVERY"}
PAGE = 100


def _iso(d: datetime) -> str:
    return d.astimezone(VN_TZ).strftime("%Y-%m-%dT%H:%M:%S+07:00")


def _status(o: dict[str, Any]) -> str:
    st = o.get("statuses")
    if isinstance(st, list):
        return str(st[0]) if st else ""
    return str(st or "")


def _epoch(s: Any) -> int:
    try:
        return int(datetime.strptime(str(s)[:25], "%Y-%m-%d %H:%M:%S %z").timestamp())
    except ValueError:
        return 0


def list_orders(c: LazadaClient, kind: str, start: datetime, end: datetime) -> Iterator[dict[str, Any]]:
    """`kind`: `update` hoặc `created`."""
    for a, b in windows(start, end):
        offset = 0
        while True:
            r = c.get(
                "/orders/get",
                **{f"{kind}_after": _iso(a), f"{kind}_before": _iso(b)},
                offset=offset,
                limit=PAGE,
                sort_by="updated_at" if kind == "update" else "created_at",
                sort_direction="ASC",
            )
            orders = r.get("orders") or []
            yield from orders
            if len(orders) < PAGE:
                break
            offset += PAGE


def _order(o: dict[str, Any]) -> dict[str, Any]:
    addr = o.get("address_shipping") or {}
    full = ", ".join(
        str(addr[k]) for k in ("address1", "address2", "address3", "address4", "address5", "city") if addr.get(k)
    ) or o.get("address_full")
    return {
        "order_id": str(o.get("order_id")),
        "created_at": o.get("created_at"),
        "updated_at": o.get("updated_at"),
        "statuses": _status(o),
        "currency": o.get("currency") or "VND",
        "price": o.get("price"),
        "shipping_fee": o.get("shipping_fee"),
        "voucher_seller": o.get("voucher_seller"),
        "voucher_platform": o.get("voucher_platform"),
        "customer_first_name": o.get("customer_first_name") or addr.get("first_name"),
        "address_phone": addr.get("phone") or o.get("address_phone"),
        "address_full": full,
    }


class OrderFetcher:
    def __init__(self, c: LazadaClient, now: datetime, rescan: list[str]) -> None:
        self.c, self.now, self.rescan = c, now, rescan
        self._orders: list[dict[str, Any]] | None = None
        self._items: list[dict[str, Any]] = []

    def _load(self, state: dict[str, Any]) -> None:
        if self._orders is not None:
            return
        start, _ = cursor_start(state, "orders_cursor", self.now)
        found = {str(o["order_id"]): o for o in list_orders(self.c, "update", start, self.now)}
        for oid in self.rescan:
            if oid not in found:
                o = self.c.get("/order/get", order_id=oid)
                if o.get("order_id"):
                    found[oid] = o
        max_upd = int(state.get("orders_cursor") or 0)
        self._orders = [_order(o) for o in found.values()]
        for o in self._orders:
            max_upd = max(max_upd, _epoch(o["updated_at"]))
        ids = list(found)
        for i in range(0, len(ids), 50):
            r = self.c.get("/orders/items/get", order_ids=json.dumps([int(x) for x in ids[i : i + 50]]))
            for entry in r.get("items") or []:
                for it in entry.get("order_items") or []:
                    self._items.append(
                        {
                            "order_item_id": str(it.get("order_item_id")),
                            "order_id": str(it.get("order_id")),
                            "name": it.get("name"),
                            "sku": it.get("sku"),
                            "shop_sku": it.get("shop_sku"),
                            "item_price": it.get("item_price"),
                            "paid_price": it.get("paid_price"),
                            "voucher_seller": it.get("voucher_seller"),
                            "voucher_platform": it.get("voucher_platform"),
                            "status": it.get("status"),
                            "created_at": it.get("created_at"),
                            "updated_at": it.get("updated_at"),
                        }
                    )
        state["orders_cursor"] = max_upd or int(self.now.timestamp())

    def orders(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        self._load(state)
        return list(self._orders or [])

    def items(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        self._load(state)
        return self._items


def transactions(c: LazadaClient, now: datetime, state: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Giao dịch tài chính theo ngày (luôn lấy lại 30 ngày vì quyết toán đến muộn)."""
    today = now.astimezone(VN_TZ).date()
    last = state.get("tx_last_date")
    first = (
        today - timedelta(days=90)
        if last is None
        else min(datetime.fromisoformat(str(last)).date(), today - timedelta(days=30))
    )
    d = first
    while d < today:
        end = min(d + timedelta(days=6), today - timedelta(days=1))
        offset = 0
        while True:
            r = c.get(
                "/finance/transaction/details/get",
                start_time=d.isoformat(),
                end_time=end.isoformat(),
                offset=offset,
                limit=500,
            )
            rows = r.get("items") or r.get("transactions") or []
            for t in rows:
                yield {
                    "transaction_id": str(t.get("transaction_number") or t.get("transaction_id")),
                    "transaction_date": t.get("transaction_date"),
                    "transaction_type": t.get("transaction_type"),
                    "fee_name": t.get("fee_name"),
                    "amount": t.get("amount"),
                    "order_no": str(t.get("order_no")),
                    "order_item_no": str(t.get("orderItem_no") or t.get("order_item_no") or ""),
                }
            if len(rows) < 500:
                break
            offset += 500
        d = end + timedelta(days=1)
    state["tx_last_date"] = (today - timedelta(days=1)).isoformat()


def returns(c: LazadaClient, state: dict[str, Any]) -> Iterator[dict[str, Any]]:
    page = 1
    while True:
        r = c.get("/reverse/getreverseordersforseller", page_size=50, page_no=page)
        items = r.get("items") or []
        for ro in items:
            for line in ro.get("reverse_order_lines") or []:
                created = line.get("return_order_line_gmt_create")
                created_s = (
                    datetime.fromtimestamp(int(created) / 1000, tz=VN_TZ).strftime("%Y-%m-%d %H:%M:%S %z")
                    if created
                    else None
                )
                yield {
                    "reverse_order_id": str(ro.get("reverse_order_id")),
                    "order_id": str(ro.get("trade_order_id")),
                    "order_item_id": str(line.get("trade_order_line_id")),
                    "created_at": created_s,
                    "reason_text": line.get("reason_text"),
                    "refund_amount": line.get("refund_amount"),
                    "status": line.get("reverse_status") or line.get("status"),
                }
        if len(items) < 50:
            break
        page += 1


def products(c: LazadaClient) -> Iterator[dict[str, Any]]:
    offset = 0
    while True:
        r = c.get("/products/get", filter="all", offset=offset, limit=50)
        prods = r.get("products") or []
        for p in prods:
            attrs = p.get("attributes") or {}
            for s in p.get("skus") or []:
                yield {
                    "item_id": p.get("item_id"),
                    "sku_id": s.get("SkuId"),
                    "seller_sku": s.get("SellerSku"),
                    "name": attrs.get("name"),
                    "primary_category": str(p.get("primary_category") or ""),
                    "ean_code": s.get("ean_code") or s.get("barcode_ean"),
                }
        if len(prods) < 50:
            break
        offset += 50


def daily_totals(c: LazadaClient, now: datetime, state: dict[str, Any]) -> Iterator[dict[str, Any]]:
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
        n, gross = 0, 0.0
        for o in list_orders(c, "created", start, start + timedelta(days=1)):
            n += 1
            gross += float(o.get("price") or 0)
        yield {"date": d.isoformat(), "order_count": n, "gross_amount": round(gross), "currency": "VND"}
        d += timedelta(days=1)
    state["totals_last_date"] = (today - timedelta(days=1)).isoformat()
