"""TikTok Shop giả lập cho test (respx). Dữ liệu từ `fixtures/`, không có dữ liệu thật."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import httpx
import respx

from connectors.tiktok_shop.client import sign

FIX = Path(__file__).parent / "fixtures"
API = "https://open-api.test.tiktok"
AUTH = "https://auth.test.tiktok"
APP = {
    "app_key": "test-app-key",
    "app_secret": "test-app-secret",
    "service_id": "7000",
    "api_base": API,
    "auth_base": AUTH,
}


class FakeTikTok:
    def __init__(self) -> None:
        data = json.loads((FIX / "orders.json").read_text(encoding="utf-8"))
        self.orders: list[dict[str, Any]] = data["orders"]
        self.data = data
        self.valid_token = "tt-1"
        self.refresh_ok = True
        self.rate_limit_next = 0
        self.refreshes = 0
        self.calls: list[str] = []

    def _ok(self, data: Any) -> httpx.Response:
        return httpx.Response(200, json={"code": 0, "message": "Success", "data": data})

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        path = url.path
        p = dict(url.params)
        self.calls.append(path)
        if url.host == httpx.URL(AUTH).host:
            self.refreshes += 1
            if not self.refresh_ok:
                return httpx.Response(200, json={"code": 105003, "message": "refresh token invalid"})
            self.valid_token = f"tt-{self.refreshes + 1}"
            return self._ok(
                {
                    "access_token": self.valid_token,
                    "refresh_token": "trt-new",
                    "access_token_expire_in": 1792000000 + 7 * 86400,
                }
            )
        if self.rate_limit_next:
            self.rate_limit_next -= 1
            return httpx.Response(429, json={"code": 36009004, "message": "rate limit"})
        if request.headers.get("x-tts-access-token") != self.valid_token:
            return httpx.Response(200, json={"code": 105002, "message": "access token expired"})
        body = request.content.decode() if request.content else ""
        expect = sign(APP["app_secret"], path, {k: v for k, v in p.items()}, body)
        assert p["sign"] == expect, "chữ ký sai"
        b = json.loads(body) if body else {}
        if path == "/order/202309/orders/search":
            field = "update_time" if "update_time_ge" in b else "create_time"
            hits = [o for o in self.orders if b[f"{field}_ge"] <= o[field] < b[f"{field}_lt"]]
            idx = int(p.get("page_token") or 0)
            nxt = str(idx + 1) if idx + 1 < len(hits) else ""
            return self._ok(
                {"orders": copy.deepcopy(hits[idx : idx + 1]), "next_page_token": nxt, "total_count": len(hits)}
            )
        if path == "/order/202309/orders":
            ids = p["ids"].split(",")
            return self._ok({"orders": [copy.deepcopy(o) for o in self.orders if o["id"] in ids]})
        if path.startswith("/finance/202309/orders/"):
            return self._ok(self.data["statement"])
        if path == "/return_refund/202309/returns/search":
            rows = [
                x
                for x in self.data["returns"]["return_orders"]
                if b["update_time_ge"] <= x["update_time"] < b["update_time_lt"]
            ]
            return self._ok({"return_orders": rows, "next_page_token": ""})
        if path == "/product/202309/products/search":
            return self._ok({**self.data["products"], "next_page_token": ""})
        if path.startswith("/product/202309/products/"):
            return self._ok(self.data["product_details"][path.rsplit("/", 1)[1]])
        if path == "/authorization/202309/shops":
            return self._ok({"shops": [{"id": "7000001", "cipher": "ROW_cipher", "name": "Demo Shop", "region": "VN"}]})
        return httpx.Response(404, json={"code": 40004, "message": "not found"})

    def mock(self) -> respx.MockRouter:
        router = respx.mock(assert_all_called=False)
        router.route(host=httpx.URL(API).host).mock(side_effect=self.handle)
        router.route(host=httpx.URL(AUTH).host).mock(side_effect=self.handle)
        return router
