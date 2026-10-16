"""OAuth gian hàng trên sàn (spec 01 §2.3, spec 05 §6.7): chữ ký, URL cấp quyền, đổi mã lấy token.

Dùng chung cho API (luồng kết nối) và connector (ký request, làm mới token). Khóa ứng dụng đối tác nằm ở secret
`dx-<source>-app` (JSON), không bao giờ ở code hay `tenants/*.yml`:

| Sàn | Trường trong `dx-<source>-app` |
|---|---|
| shopee | `partner_id`, `partner_key`, tùy chọn `api_base` (mặc định production) |
| tiktok_shop | `app_key`, `app_secret`, `service_id`, tùy chọn `api_base`, `auth_base` |
| lazada | `app_key`, `app_secret`, tùy chọn `api_base`, `auth_base` |
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

SOURCES = ("shopee", "tiktok_shop", "lazada")

SHOPEE_BASE = "https://partner.shopeemobile.com"
TIKTOK_API = "https://open-api.tiktokglobalshop.com"
TIKTOK_AUTH = "https://auth.tiktok-shops.com"
TIKTOK_AUTHORIZE = "https://services.tiktokshop.com/open/authorize"
LAZADA_API = "https://api.lazada.vn/rest"
LAZADA_AUTH = "https://auth.lazada.com"


class OAuthError(Exception):
    """Sàn từ chối đổi mã hoặc phản hồi không đúng dạng. Không chứa token."""


@dataclass
class TokenResult:
    account_id: str
    secret: dict[str, Any]  # JSON ghi vào `dx-<tenant>-<source>-<account>`
    extra: dict[str, Any] = field(default_factory=dict)


def hmac_sha256(key: str, msg: str) -> str:
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()


def _iso_in(seconds: int) -> str:
    from datetime import timedelta

    from dx_common.timeutil import iso_z, now_utc

    return iso_z(now_utc() + timedelta(seconds=max(int(seconds), 0)))


# ---------------------------------------------------------------- Shopee


def shopee_public_params(app: dict[str, Any], path: str, ts: int) -> dict[str, Any]:
    pid = int(app["partner_id"])
    return {"partner_id": pid, "timestamp": ts, "sign": hmac_sha256(str(app["partner_key"]), f"{pid}{path}{ts}")}


def shopee_authorize_url(app: dict[str, Any], redirect: str, ts: int | None = None) -> str:
    path = "/api/v2/shop/auth_partner"
    p = shopee_public_params(app, path, ts or int(time.time()))
    return str(httpx.URL(f"{app.get('api_base') or SHOPEE_BASE}{path}", params={**p, "redirect": redirect}))


def shopee_exchange(app: dict[str, Any], code: str, shop_id: str, client: httpx.Client) -> TokenResult:
    path = "/api/v2/auth/token/get"
    r = client.post(
        f"{app.get('api_base') or SHOPEE_BASE}{path}",
        params=shopee_public_params(app, path, int(time.time())),
        json={"code": code, "shop_id": int(shop_id), "partner_id": int(app["partner_id"])},
    )
    body = r.json() if r.content else {}
    if r.status_code != 200 or body.get("error") or not body.get("access_token"):
        raise OAuthError(f"shopee: {body.get('error') or r.status_code}")
    return TokenResult(
        str(shop_id),
        {
            "shop_id": str(shop_id),
            "access_token": body["access_token"],
            "refresh_token": body["refresh_token"],
            "expires_at": _iso_in(int(body.get("expire_in", 14400))),
        },
    )


# ---------------------------------------------------------------- TikTok Shop


def tiktok_sign(app_secret: str, path: str, params: dict[str, Any], body: str = "") -> str:
    items = "".join(f"{k}{params[k]}" for k in sorted(params) if k not in ("sign", "access_token"))
    return hmac_sha256(app_secret, f"{app_secret}{path}{items}{body}{app_secret}")


def tiktok_authorize_url(app: dict[str, Any], state: str) -> str:
    return str(
        httpx.URL(
            str(app.get("authorize_base") or TIKTOK_AUTHORIZE), params={"service_id": app["service_id"], "state": state}
        )
    )


def tiktok_expiry(data: dict[str, Any]) -> str:
    exp = int(data.get("access_token_expire_in") or 0)
    if exp > 10**9:  # mốc epoch
        return _iso_in(exp - int(time.time()))
    return _iso_in(exp or 3600)


def tiktok_exchange(app: dict[str, Any], code: str, client: httpx.Client) -> TokenResult:
    r = client.get(
        f"{app.get('auth_base') or TIKTOK_AUTH}/api/v2/token/get",
        params={
            "app_key": app["app_key"],
            "app_secret": app["app_secret"],
            "auth_code": code,
            "grant_type": "authorized_code",
        },
    )
    body = r.json() if r.content else {}
    data = body.get("data") or {}
    if r.status_code != 200 or body.get("code") or not data.get("access_token"):
        raise OAuthError(f"tiktok_shop: {body.get('code') or r.status_code}")
    token = data["access_token"]
    path = "/authorization/202309/shops"
    q: dict[str, Any] = {"app_key": app["app_key"], "timestamp": int(time.time())}
    q["sign"] = tiktok_sign(str(app["app_secret"]), path, q)
    s = client.get(f"{app.get('api_base') or TIKTOK_API}{path}", params=q, headers={"x-tts-access-token": token})
    shops = ((s.json() if s.content else {}).get("data") or {}).get("shops") or []
    if not shops:
        raise OAuthError("tiktok_shop: tài khoản không có shop nào")
    shop = shops[0]
    return TokenResult(
        str(shop["id"]),
        {
            "shop_id": str(shop["id"]),
            "shop_cipher": shop.get("cipher"),
            "access_token": token,
            "refresh_token": data["refresh_token"],
            "expires_at": tiktok_expiry(data),
        },
        {"shop_name": shop.get("name"), "other_shops": [str(x["id"]) for x in shops[1:]]},
    )


# ---------------------------------------------------------------- Lazada


def lazada_sign(app_secret: str, api_path: str, params: dict[str, Any]) -> str:
    items = "".join(f"{k}{params[k]}" for k in sorted(params) if k != "sign")
    return hmac_sha256(app_secret, f"{api_path}{items}").upper()


def lazada_authorize_url(app: dict[str, Any], redirect: str, state: str) -> str:
    return str(
        httpx.URL(
            f"{app.get('auth_base') or LAZADA_AUTH}/oauth/authorize",
            params={
                "response_type": "code",
                "force_auth": "true",
                "redirect_uri": redirect,
                "client_id": app["app_key"],
                "state": state,
            },
        )
    )


def lazada_exchange(app: dict[str, Any], code: str, client: httpx.Client) -> TokenResult:
    api_path = "/auth/token/create"
    p: dict[str, Any] = {
        "app_key": app["app_key"],
        "timestamp": int(time.time() * 1000),
        "sign_method": "sha256",
        "code": code,
    }
    p["sign"] = lazada_sign(str(app["app_secret"]), api_path, p)
    r = client.post(f"{app.get('auth_base') or LAZADA_AUTH}/rest{api_path}", data=p)
    body = r.json() if r.content else {}
    if r.status_code != 200 or str(body.get("code", "0")) != "0" or not body.get("access_token"):
        raise OAuthError(f"lazada: {body.get('code') or r.status_code}")
    info = [u for u in body.get("country_user_info") or [] if str(u.get("country", "")).lower() == "vn"] or list(
        body.get("country_user_info") or [{}]
    )
    seller = str(info[0].get("seller_id") or info[0].get("user_id") or body.get("account") or "")
    if not seller:
        raise OAuthError("lazada: không xác định được seller_id")
    return TokenResult(
        seller,
        {
            "seller_id": seller,
            "access_token": body["access_token"],
            "refresh_token": body["refresh_token"],
            "expires_at": _iso_in(int(body.get("expires_in", 3600))),
        },
    )
