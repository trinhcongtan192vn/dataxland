"""Client Shopee Open Platform API v2: ký HMAC-SHA256, làm mới token, phân loại lỗi (spec 01 §3)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from connectors.base import SourceError
from connectors.common.http import AuthExpired, HttpClient, RateLimited, TransientError
from connectors.common.tokens import AuthRevoked, TokenManager
from dx_common.marketplace import hmac_sha256, shopee_authorize_url, shopee_public_params

PROD_BASE = "https://partner.shopeemobile.com"
TEST_BASE = "https://partner.test-stable.shopeemobile.com"
AUTH_ERRORS = {"error_auth", "invalid_access_token", "error_permission", "invalid_acceess_token"}
REVOKED_ERRORS = {"error_auth", "error_param_refresh_token", "invalid_refresh_token", "error_permission"}


# Chữ ký và URL cấp quyền dùng chung với API (luồng kết nối, spec 05 §6.7).
sign = hmac_sha256
public_params = shopee_public_params
authorize_url = shopee_authorize_url


class ShopeeHttp(HttpClient):
    def check(self, resp: httpx.Response, body: Any) -> None:
        err = str((body or {}).get("error") or "") if isinstance(body, dict) else ""
        if resp.status_code == 429 or err in ("error_too_many_request", "error_rate_limit"):
            raise RateLimited(None)
        if err in AUTH_ERRORS or resp.status_code in (401, 403):
            raise AuthExpired()
        if resp.status_code >= 500 or err in ("error_server", "error_inner", "error_busi_system_busy"):
            raise TransientError(err or str(resp.status_code))
        if err:
            raise SourceError("api_error", f"shopee {err}")
        if resp.status_code >= 400:
            raise SourceError("api_error", f"HTTP {resp.status_code}")


def refresh_token(app: dict[str, Any], data: dict[str, Any], http: ShopeeHttp | None = None) -> dict[str, Any]:
    path = "/api/v2/auth/access_token/get"
    c = http or ShopeeHttp(str(app.get("api_base") or PROD_BASE))
    try:
        body = c.send(
            "POST",
            path,
            params=public_params(app, path, int(time.time())),
            json={
                "refresh_token": data.get("refresh_token"),
                "shop_id": int(data["shop_id"]),
                "partner_id": int(app["partner_id"]),
            },
        )
    except (AuthExpired, SourceError) as exc:
        raise AuthRevoked() from exc
    return {
        "access_token": body["access_token"],
        "refresh_token": body["refresh_token"],
        "expires_in": int(body.get("expire_in", 14400)),
    }


class ShopeeClient:
    """Gọi API của shop; tự làm mới token một lần khi nguồn báo hết hạn."""

    def __init__(
        self, tokens: TokenManager, http: ShopeeHttp | None = None, clock: Callable[[], float] = time.time
    ) -> None:
        self.tokens = tokens
        self.app = tokens.app
        self.http = http or ShopeeHttp(str(self.app.get("api_base") or PROD_BASE))
        self.clock = clock

    def _params(self, path: str, extra: dict[str, Any]) -> dict[str, Any]:
        ts = int(self.clock())
        pid = int(self.app["partner_id"])
        shop_id = int(self.tokens.data["shop_id"])
        at = self.tokens.access_token
        base = f"{pid}{path}{ts}{at}{shop_id}"
        return {
            "partner_id": pid,
            "timestamp": ts,
            "access_token": at,
            "shop_id": shop_id,
            "sign": sign(str(self.app["partner_key"]), base),
            **extra,
        }

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        for attempt in (0, 1):
            try:
                body = self.http.send("GET", path, params=self._params(path, params))
                return dict(body.get("response") or {})
            except AuthExpired:
                if attempt:
                    raise SourceError("auth_revoked", f"{path}: token bị từ chối sau khi làm mới") from None
                self.tokens.refresh()
        raise AssertionError("unreachable")
