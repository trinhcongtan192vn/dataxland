"""Shopee giả lập cho test (respx). Dữ liệu từ `fixtures/`, không có dữ liệu thật."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import httpx
import respx

FIX = Path(__file__).parent / "fixtures"
BASE = "https://partner.test-stable.shopeemobile.com"


def fixture(name: str) -> Any:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


class FakeShopee:
    def __init__(self) -> None:
        self.orders: list[dict[str, Any]] = fixture("order_detail.json")["order_list"]
        self.escrow = fixture("escrow.json")
        self.returns = fixture("returns.json")
        self.products = fixture("products.json")
        self.valid_token = "at-1"
        self.refresh_ok = True
        self.rate_limit_next = 0
        self.calls: list[str] = []
        self.refreshes = 0

    def set_status(self, sn: str, status: str, update_time: int) -> None:
        for o in self.orders:
            if o["order_sn"] == sn:
                o["order_status"] = status
                o["update_time"] = update_time

    def _ok(self, response: Any) -> httpx.Response:
        return httpx.Response(200, json={"error": "", "message": "", "response": response})

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        p = dict(request.url.params)
        self.calls.append(path)
        if path == "/api/v2/auth/access_token/get":
            self.refreshes += 1
            if not self.refresh_ok:
                return httpx.Response(200, json={"error": "error_param_refresh_token", "message": "invalid"})
            self.valid_token = f"at-{self.refreshes + 1}"
            return httpx.Response(
                200, json={"error": "", "access_token": self.valid_token, "refresh_token": "rt-new", "expire_in": 14400}
            )
        if self.rate_limit_next:
            self.rate_limit_next -= 1
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "error_too_many_request"})
        if p.get("access_token") != self.valid_token:
            return httpx.Response(200, json={"error": "invalid_access_token", "message": "expired"})
        assert p.get("sign") and len(p["sign"]) == 64
        if path == "/api/v2/order/get_order_list":
            field = p["time_range_field"]
            lo, hi = int(p["time_from"]), int(p["time_to"])
            hits = [o for o in self.orders if lo <= o[field] < hi]
            # Một đơn mỗi trang để phủ phân trang.
            idx = int(p.get("cursor") or 0)
            page = hits[idx : idx + 1]
            more = idx + 1 < len(hits)
            return self._ok(
                {
                    "more": more,
                    "next_cursor": str(idx + 1) if more else "",
                    "order_list": [{"order_sn": o["order_sn"], "order_status": o["order_status"]} for o in page],
                }
            )
        if path == "/api/v2/order/get_order_detail":
            sns = p["order_sn_list"].split(",")
            return self._ok({"order_list": [copy.deepcopy(o) for o in self.orders if o["order_sn"] in sns]})
        if path == "/api/v2/payment/get_escrow_detail":
            return self._ok({"order_sn": p["order_sn"], **self.escrow})
        if path == "/api/v2/returns/get_return_list":
            lo, hi = int(p["update_time_from"]), int(p["update_time_to"])
            rows = [x for x in self.returns["return"] if lo <= x["update_time"] < hi]
            return self._ok({"more": False, "return": rows})
        if path == "/api/v2/product/get_item_list":
            return self._ok(self.products["item_list"])
        if path == "/api/v2/product/get_item_base_info":
            return self._ok(self.products["base_info"])
        if path == "/api/v2/product/get_model_list":
            return self._ok(self.products["models"][p["item_id"]])
        return httpx.Response(404, json={"error": "error_not_found"})

    def mock(self) -> respx.MockRouter:
        router = respx.mock(base_url=BASE, assert_all_called=False)
        router.route().mock(side_effect=self.handle)
        return router
