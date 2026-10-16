"""Client TikTok Shop Partner API (phiên bản 202309): ký HMAC-SHA256, làm mới token, phân loại lỗi (spec 01 §4)."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import httpx

from connectors.base import SourceError
from connectors.common.http import AuthExpired, HttpClient, RateLimited, TransientError
from connectors.common.tokens import AuthRevoked, TokenManager
from dx_common.marketplace import tiktok_authorize_url, tiktok_sign

API_BASE = "https://open-api.tiktokglobalshop.com"
AUTH_BASE = "https://auth.tiktok-shops.com"
AUTH_CODES = {105000, 105001, 105002, 105003, 105005, 36004004}
RATE_CODES = {36009004, 429}


# Chữ ký và URL cấp quyền dùng chung với API (luồng kết nối, spec 05 §6.7).
sign = tiktok_sign
authorize_url = tiktok_authorize_url


class TikTokHttp(HttpClient):
    def check(self, resp: httpx.Response, body: Any) -> None:
        code = int((body or {}).get("code", 0)) if isinstance(body, dict) else 0
        if resp.status_code == 429 or code in RATE_CODES:
            raise RateLimited(None)
        if resp.status_code == 401 or code in AUTH_CODES:
            raise AuthExpired()
        if resp.status_code >= 500 or code in (36009003, 1000):
            raise TransientError(str(code or resp.status_code))
        if code:
            raise SourceError("api_error", f"tiktok_shop code {code}")
        if resp.status_code >= 400:
            raise SourceError("api_error", f"HTTP {resp.status_code}")


def _token_body(data: dict[str, Any]) -> dict[str, Any]:
    exp = int(data.get("access_token_expire_in") or 0)
    out = {"access_token": data["access_token"], "refresh_token": data["refresh_token"]}
    if exp > 10**9:  # TikTok trả mốc epoch hết hạn
        out["expires_in"] = max(exp - int(time.time()), 0)
    elif exp:
        out["expires_in"] = exp
    return out


def refresh_token(app: dict[str, Any], data: dict[str, Any], http: TikTokHttp | None = None) -> dict[str, Any]:
    c = http or TikTokHttp(str(app.get("auth_base") or AUTH_BASE))
    try:
        body = c.send(
            "GET",
            f"{app.get('auth_base') or AUTH_BASE}/api/v2/token/refresh",
            params={
                "app_key": app["app_key"],
                "app_secret": app["app_secret"],
                "refresh_token": data.get("refresh_token"),
                "grant_type": "refresh_token",
            },
        )
    except (AuthExpired, SourceError) as exc:
        raise AuthRevoked() from exc
    return _token_body(body.get("data") or {})


class TikTokClient:
    def __init__(
        self, tokens: TokenManager, http: TikTokHttp | None = None, clock: Callable[[], float] = time.time
    ) -> None:
        self.tokens = tokens
        self.app = tokens.app
        self.base = str(self.app.get("api_base") or API_BASE)
        self.http = http or TikTokHttp(self.base)
        self.clock = clock

    def call(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        *,
        shop: bool = True,
    ) -> dict[str, Any]:
        for attempt in (0, 1):
            q: dict[str, Any] = {"app_key": self.app["app_key"], "timestamp": int(self.clock()), **(params or {})}
            if shop and self.tokens.data.get("shop_cipher"):
                q["shop_cipher"] = self.tokens.data["shop_cipher"]
            raw = json.dumps(body, separators=(",", ":")) if body is not None else ""
            q["sign"] = sign(str(self.app["app_secret"]), path, q, raw)
            headers = {"x-tts-access-token": self.tokens.access_token, "content-type": "application/json"}
            try:
                res = self.http.send(method, f"{self.base}{path}", params=q, content=raw or None, headers=headers)
                return dict(res.get("data") or {})
            except AuthExpired:
                if attempt:
                    raise SourceError("auth_revoked", f"{path}: token bị từ chối sau khi làm mới") from None
                self.tokens.refresh()
        raise AssertionError("unreachable")

    def shops(self) -> list[dict[str, Any]]:
        return list(self.call("GET", "/authorization/202309/shops", shop=False).get("shops") or [])
