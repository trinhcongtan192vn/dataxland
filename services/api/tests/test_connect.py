"""Kết nối sàn qua OAuth (spec 05 §6.7) và trạng thái tích hợp (ADR 0001)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from tests.conftest import auth

SHOPEE = "https://partner.test-stable.shopeemobile.com"
TT_API = "https://open-api.test.tiktok"
TT_AUTH = "https://auth.test.tiktok"


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Any]:
    from dx_common.secrets import LocalFileSecretStore, set_secret_store

    s = LocalFileSecretStore(tmp_path / "secrets")
    set_secret_store(s)
    yield s
    set_secret_store(None)


def _shopee_app(store: Any) -> None:
    store.put("dx-shopee-app", json.dumps({"partner_id": 2001234, "partner_key": "pk", "api_base": SHOPEE}))


def _start(client: Any, source: str, key: str = "data_lead") -> Any:
    return client.post(f"/v1/connect/{source}/start", headers=auth(key, "demo_seller"))


def test_start_requires_data_lead(client: Any, store: Any) -> None:
    _shopee_app(store)
    assert _start(client, "shopee", "owner_seller").status_code == 403
    assert _start(client, "shopee", "engineer").status_code == 403


def test_start_without_app_secret_points_to_guide(client: Any, store: Any) -> None:
    r = _start(client, "shopee")
    assert r.status_code == 409
    assert r.json()["code"] == "APP_NOT_CONFIGURED"
    assert "/ops/integrations/shopee" in r.json()["detail"]


def test_shopee_connect_flow_writes_secret(client: Any, store: Any, session: Any) -> None:
    from sqlalchemy import select

    from app.db.models import AuditLog, SourceSync

    _shopee_app(store)
    r = _start(client, "shopee")
    assert r.status_code == 200, r.text
    url = urlparse(r.json()["authorize_url"])
    redirect = parse_qs(url.query)["redirect"][0]
    assert redirect.startswith("http://localhost:8000/v1/connect/shopee/callback?state=")
    state = parse_qs(urlparse(redirect).query)["state"][0]
    with respx.mock(assert_all_called=True) as m:
        m.post(f"{SHOPEE}/api/v2/auth/token/get").mock(
            return_value=httpx.Response(
                200, json={"error": "", "access_token": "AT-SECRET", "refresh_token": "RT-SECRET", "expire_in": 14400}
            )
        )
        cb = client.get(
            "/v1/connect/shopee/callback",
            params={"state": state, "code": "c1", "shop_id": "100001"},
            follow_redirects=False,
        )
    assert cb.status_code == 302
    loc = cb.headers["location"]
    assert loc.startswith("https://app.test/ops/tenants/demo_seller?connected=shopee")
    assert "AT-SECRET" not in loc and "RT-SECRET" not in cb.text
    secret = json.loads(store.get("dx-demo_seller-shopee-100001"))
    assert secret["access_token"] == "AT-SECRET" and secret["shop_id"] == "100001" and secret["expires_at"]
    sync = session.scalar(
        select(SourceSync).where(SourceSync.tenant_id == "demo_seller", SourceSync.source == "shopee")
    )
    assert sync is not None and sync.connected_at is not None
    logs = [a.detail for a in session.scalars(select(AuditLog).where(AuditLog.action == "source.connected"))]
    assert logs and "AT-SECRET" not in json.dumps(logs)
    # State dùng một lần.
    again = client.get(
        "/v1/connect/shopee/callback",
        params={"state": state, "code": "c1", "shop_id": "100001"},
        follow_redirects=False,
    )
    assert "connect_error=STATE_INVALID" in again.headers["location"]


def test_callback_bad_state(client: Any, store: Any) -> None:
    r = client.get(
        "/v1/connect/shopee/callback", params={"state": "nope", "code": "x", "shop_id": "1"}, follow_redirects=False
    )
    assert r.status_code == 302 and "connect_error=STATE_INVALID" in r.headers["location"]


def test_callback_exchange_failure(client: Any, store: Any) -> None:
    _shopee_app(store)
    redirect = parse_qs(urlparse(_start(client, "shopee").json()["authorize_url"]).query)["redirect"][0]
    state = parse_qs(urlparse(redirect).query)["state"][0]
    with respx.mock() as m:
        m.post(f"{SHOPEE}/api/v2/auth/token/get").mock(
            return_value=httpx.Response(200, json={"error": "error_auth", "message": "invalid code"})
        )
        r = client.get(
            "/v1/connect/shopee/callback",
            params={"state": state, "code": "bad", "shop_id": "1"},
            follow_redirects=False,
        )
    assert "connect_error=EXCHANGE_FAILED" in r.headers["location"]
    assert not store.exists("dx-demo_seller-shopee-1")


def test_tiktok_connect_flow(client: Any, store: Any) -> None:
    store.put(
        "dx-tiktok_shop-app",
        json.dumps({"app_key": "k", "app_secret": "s", "service_id": "77", "api_base": TT_API, "auth_base": TT_AUTH}),
    )
    r = _start(client, "tiktok_shop")
    q = parse_qs(urlparse(r.json()["authorize_url"]).query)
    assert q["service_id"] == ["77"]
    with respx.mock() as m:
        m.get(f"{TT_AUTH}/api/v2/token/get").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {"access_token": "TA", "refresh_token": "TR", "access_token_expire_in": 4102444800},
                },
            )
        )
        m.get(f"{TT_API}/authorization/202309/shops").mock(
            return_value=httpx.Response(
                200, json={"code": 0, "data": {"shops": [{"id": "7000001", "cipher": "ROW_x", "name": "Shop"}]}}
            )
        )
        cb = client.get(
            "/v1/connect/tiktok_shop/callback", params={"state": q["state"][0], "code": "c"}, follow_redirects=False
        )
    assert "connected=tiktok_shop" in cb.headers["location"]
    sec = json.loads(store.get("dx-demo_seller-tiktok_shop-7000001"))
    assert sec["shop_cipher"] == "ROW_x"


def test_integrations_status_never_returns_values(client: Any, store: Any) -> None:
    _shopee_app(store)
    assert client.get("/v1/ops/integrations", headers=auth("owner_seller")).status_code == 403
    r = client.get("/v1/ops/integrations", headers=auth("data_lead"))
    assert r.status_code == 200, r.text
    rows = {x["key"]: x for x in r.json()}
    assert {"shopee", "tiktok_shop", "lazada", "windsor", "telegram", "firebase", "smtp", "fx_vcb"} <= set(rows)
    shopee = rows["shopee"]
    app_check = next(c for c in shopee["checks"] if c["name"] == "dx-shopee-app")
    assert app_check["configured"] is True
    assert {t["tenant_id"] for t in shopee["tenants"]} >= {"demo_seller"}
    assert "pk" not in r.text and "test-webhook-secret" not in r.text
    d = client.get("/v1/ops/integrations/shopee", headers=auth("engineer"))
    assert d.status_code == 200 and "open.shopee.com" in d.json()["guide_md"]
    assert client.get("/v1/ops/integrations/khong-co", headers=auth("data_lead")).status_code == 404
