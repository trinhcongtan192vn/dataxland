"""Client Lazada Open Platform (spec 01 §5): ký HMAC-SHA256 (chữ hoa), làm mới token, phân loại lỗi."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from connectors.base import SourceError
from connectors.common.http import AuthExpired, HttpClient, RateLimited, TransientError
from connectors.common.tokens import AuthRevoked, TokenManager
from dx_common.marketplace import LAZADA_API, LAZADA_AUTH, lazada_sign

AUTH_CODES = {"IllegalAccessToken", "MissingAccessToken", "AccessTokenExpired", "InvalidAccessToken"}
RATE_CODES = {"ApiCallLimit", "AppCallLimit", "SellerCallLimit", "ServiceTimeout429"}
TRANSIENT_CODES = {"ServiceTimeout", "InternalError", "SystemError", "ServiceUnavailable"}


class LazadaHttp(HttpClient):
    def check(self, resp: httpx.Response, body: Any) -> None:
        code = str((body or {}).get("code", "0")) if isinstance(body, dict) else "0"
        if resp.status_code == 429 or code in RATE_CODES:
            raise RateLimited(None)
        if resp.status_code == 401 or code in AUTH_CODES:
            raise AuthExpired()
        if resp.status_code >= 500 or code in TRANSIENT_CODES:
            raise TransientError(code)
        if code != "0":
            raise SourceError("api_error", f"lazada {code}")
        if resp.status_code >= 400:
            raise SourceError("api_error", f"HTTP {resp.status_code}")


def _signed(
    app: dict[str, Any], api_path: str, params: dict[str, Any], ts_ms: int, access_token: str | None = None
) -> dict[str, Any]:
    p: dict[str, Any] = {"app_key": app["app_key"], "timestamp": ts_ms, "sign_method": "sha256", **params}
    if access_token:
        p["access_token"] = access_token
    p["sign"] = lazada_sign(str(app["app_secret"]), api_path, p)
    return p


def refresh_token(app: dict[str, Any], data: dict[str, Any], http: LazadaHttp | None = None) -> dict[str, Any]:
    base = str(app.get("auth_base") or LAZADA_AUTH)
    c = http or LazadaHttp(base)
    path = "/auth/token/refresh"
    try:
        body = c.send(
            "POST",
            f"{base}/rest{path}",
            data=_signed(app, path, {"refresh_token": data.get("refresh_token")}, int(time.time() * 1000)),
        )
    except (AuthExpired, SourceError) as exc:
        raise AuthRevoked() from exc
    return {
        "access_token": body["access_token"],
        "refresh_token": body["refresh_token"],
        "expires_in": int(body.get("expires_in", 3600)),
    }


class LazadaClient:
    def __init__(
        self, tokens: TokenManager, http: LazadaHttp | None = None, clock: Callable[[], float] = time.time
    ) -> None:
        self.tokens = tokens
        self.app = tokens.app
        self.base = str(self.app.get("api_base") or LAZADA_API)
        self.http = http or LazadaHttp(self.base)
        self.clock = clock

    def get(self, api_path: str, **params: Any) -> dict[str, Any]:
        for attempt in (0, 1):
            q = _signed(self.app, api_path, params, int(self.clock() * 1000), self.tokens.access_token)
            try:
                body = self.http.send("GET", f"{self.base}{api_path}", params=q)
                data = body.get("data")
                return data if isinstance(data, dict) else {"items": data or []}
            except AuthExpired:
                if attempt:
                    raise SourceError("auth_revoked", f"{api_path}: token bị từ chối sau khi làm mới") from None
                self.tokens.refresh()
        raise AssertionError("unreachable")
