"""Lazada giả lập cho test (respx). Dữ liệu cố định, không có dữ liệu thật."""

from __future__ import annotations

import copy
import json
from datetime import datetime
from typing import Any

import httpx
import respx

from dx_common.marketplace import lazada_sign

API = "https://api.lazada.test/rest"
AUTH = "https://auth.lazada.test"
APP = {"app_key": "100001", "app_secret": "lz-secret", "api_base": API, "auth_base": AUTH}

ORDERS: list[dict[str, Any]] = [
    {
        "order_id": 826101000001,
        "created_at": "2026-10-10 09:00:00 +0700",
        "updated_at": "2026-10-14 10:00:00 +0700",
        "statuses": ["confirmed"],
        "currency": "VND",
        "price": "538000.00",
        "shipping_fee": "0.00",
        "voucher_seller": "26000.00",
        "voucher_platform": "0.00",
        "customer_first_name": "Người Mua Một",
        "address_shipping": {
            "phone": "0900000011",
            "first_name": "Người Mua Một",
            "address1": "1 Đường A",
            "city": "Hà Nội",
        },
    },
    {
        "order_id": 826101100002,
        "created_at": "2026-10-11 10:00:00 +0700",
        "updated_at": "2026-10-14 11:00:00 +0700",
        "statuses": ["shipped"],
        "currency": "VND",
        "price": "189000.00",
        "shipping_fee": "0.00",
        "voucher_seller": "0.00",
        "voucher_platform": "10000.00",
        "customer_first_name": "Người Mua Hai",
        "address_shipping": {"phone": "0900000012", "address1": "2 Đường B", "city": "TP HCM"},
    },
]
ITEMS = {
    826101000001: [
        {
            "order_item_id": 82610100000101,
            "order_id": 826101000001,
            "name": "Kem chống nắng",
            "sku": "DS-CHONG-50",
            "shop_sku": "2006_VNAMZ",
            "item_price": "269000.00",
            "paid_price": "256000.00",
            "voucher_seller": "13000.00",
            "voucher_platform": "0.00",
            "status": "confirmed",
            "created_at": "2026-10-10 09:00:00 +0700",
            "updated_at": "2026-10-14 10:00:00 +0700",
        },
        {
            "order_item_id": 82610100000102,
            "order_id": 826101000001,
            "name": "Kem chống nắng",
            "sku": "DS-CHONG-50",
            "shop_sku": "2006_VNAMZ",
            "item_price": "269000.00",
            "paid_price": "256000.00",
            "voucher_seller": "13000.00",
            "voucher_platform": "0.00",
            "status": "confirmed",
            "created_at": "2026-10-10 09:00:00 +0700",
            "updated_at": "2026-10-14 10:00:00 +0700",
        },
    ],
    826101100002: [
        {
            "order_item_id": 82610110000201,
            "order_id": 826101100002,
            "name": "Serum",
            "sku": "DS-SRM-C30",
            "shop_sku": "2000_VNAMZ",
            "item_price": "189000.00",
            "paid_price": "179000.00",
            "voucher_seller": "0.00",
            "voucher_platform": "10000.00",
            "status": "shipped",
            "created_at": "2026-10-11 10:00:00 +0700",
            "updated_at": "2026-10-14 11:00:00 +0700",
        }
    ],
}


def _ts(s: str) -> float:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z").timestamp()


def _ots(s: str) -> float:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z").timestamp()


class FakeLazada:
    def __init__(self) -> None:
        self.orders = copy.deepcopy(ORDERS)
        self.valid_token = "lz-1"
        self.refresh_ok = True
        self.refreshes = 0
        self.rate_limit_next = 0
        self.calls: list[str] = []

    def _ok(self, data: Any) -> httpx.Response:
        return httpx.Response(200, json={"code": "0", "data": data, "request_id": "r"})

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.host == httpx.URL(AUTH).host:
            self.refreshes += 1
            if not self.refresh_ok:
                return httpx.Response(200, json={"code": "IllegalRefreshToken", "message": "invalid"})
            self.valid_token = f"lz-{self.refreshes + 1}"
            return httpx.Response(
                200,
                json={"code": "0", "access_token": self.valid_token, "refresh_token": "lzr-new", "expires_in": 604800},
            )
        path = url.path.removeprefix("/rest")
        p = dict(url.params)
        self.calls.append(path)
        if self.rate_limit_next:
            self.rate_limit_next -= 1
            return httpx.Response(200, json={"code": "ApiCallLimit", "message": "limit"})
        if p.get("access_token") != self.valid_token:
            return httpx.Response(200, json={"code": "IllegalAccessToken", "message": "expired"})
        assert p["sign"] == lazada_sign(APP["app_secret"], path, {k: v for k, v in p.items() if k != "sign"})
        if path == "/orders/get":
            kind = "update" if "update_after" in p else "created"
            col = "updated_at" if kind == "update" else "created_at"
            lo, hi = _ts(p[f"{kind}_after"]), _ts(p[f"{kind}_before"])
            hits = [o for o in self.orders if lo <= _ots(o[col]) < hi]
            off, lim = int(p.get("offset", 0)), int(p.get("limit", 100))
            return self._ok({"orders": copy.deepcopy(hits[off : off + lim]), "countTotal": len(hits)})
        if path == "/order/get":
            o = next((x for x in self.orders if str(x["order_id"]) == p["order_id"]), {})
            return self._ok(copy.deepcopy(o))
        if path == "/orders/items/get":
            ids = json.loads(p["order_ids"])
            return self._ok([{"order_id": i, "order_items": ITEMS.get(i, [])} for i in ids])
        if path == "/finance/transaction/details/get":
            if p["start_time"] <= "2026-10-14" <= p["end_time"] and int(p.get("offset", 0)) == 0:
                return self._ok(
                    [
                        {
                            "transaction_date": "2026-10-14",
                            "transaction_type": "Orders-Marketing Fees",
                            "fee_name": "Commission",
                            "amount": "-35840",
                            "order_no": "826101000001",
                            "orderItem_no": "82610100000101",
                            "transaction_number": "T1",
                        },
                        {
                            "transaction_date": "2026-10-14",
                            "transaction_type": "Orders-Sales",
                            "fee_name": "Payment Fee",
                            "amount": "-10760",
                            "order_no": "826101000001",
                            "orderItem_no": "82610100000101",
                            "transaction_number": "T2",
                        },
                    ]
                )
            return self._ok([])
        if path == "/reverse/getreverseordersforseller":
            return self._ok(
                {
                    "items": [
                        {
                            "reverse_order_id": 9001,
                            "trade_order_id": 826101000001,
                            "reverse_order_lines": [
                                {
                                    "trade_order_line_id": 82610100000102,
                                    "refund_amount": 256000,
                                    "reason_text": "Change of mind",
                                    "reverse_status": "REFUND_SUCCESS",
                                    "return_order_line_gmt_create": 1792000000000,
                                }
                            ],
                        }
                    ]
                }
            )
        if path == "/products/get":
            return self._ok(
                {
                    "products": [
                        {
                            "item_id": 2000,
                            "primary_category": 10001,
                            "attributes": {"name": "Serum"},
                            "skus": [{"SkuId": 30000, "SellerSku": "DS-SRM-C30", "ean_code": "8938500000011"}],
                        }
                    ]
                }
            )
        return httpx.Response(404, json={"code": "NotFound"})

    def mock(self) -> respx.MockRouter:
        router = respx.mock(assert_all_called=False)
        router.route(host=httpx.URL(API).host).mock(side_effect=self.handle)
        router.route(host=httpx.URL(AUTH).host).mock(side_effect=self.handle)
        return router
