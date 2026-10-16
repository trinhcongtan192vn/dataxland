"""Connector TikTok Shop với API giả lập (spec 01 §11)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from connectors.base import SourceError, SyncContext
from connectors.tiktok_shop.client import TikTokHttp, authorize_url
from connectors.tiktok_shop.source import sync_tiktok_shop
from connectors.tiktok_shop.tests.fake_tiktok import API, APP, FakeTikTok
from dx_common.secrets import LocalFileSecretStore, set_secret_store
from dx_common.tenants import load_tenant_file
from dx_pipelines.warehouse import DuckDBWarehouse

REPO = Path(__file__).resolve().parents[4]
NOW = datetime(2026, 10, 16, 0, 0, tzinfo=UTC)
SECRET = "dx-demo_seller-tiktok_shop-7000001"


@pytest.fixture()
def env(tmp_path: Path) -> Iterator[dict[str, Any]]:
    store = LocalFileSecretStore(tmp_path / "secrets")
    store.put("dx-tiktok_shop-app", json.dumps(APP))
    store.put(
        SECRET,
        json.dumps(
            {
                "shop_id": "7000001",
                "shop_cipher": "ROW_cipher",
                "access_token": "tt-1",
                "refresh_token": "trt-1",
                "expires_at": "2026-10-20T00:00:00Z",
            }
        ),
    )
    set_secret_store(store)
    tenant = load_tenant_file(REPO / "tenants" / "demo_seller.yml")
    source = next(s for s in tenant.sources if s.type == "tiktok_shop").model_copy(update={"secret_ref": SECRET})
    yield {
        "tenant": tenant,
        "source": source,
        "wh": DuckDBWarehouse(tmp_path / "wh.duckdb"),
        "fake": FakeTikTok(),
        "store": store,
        "tmp": tmp_path,
    }
    set_secret_store(None)


def _ctx(env: dict[str, Any], now: datetime = NOW) -> SyncContext:
    return SyncContext(
        warehouse=env["wh"],
        raw_dataset="t_demo_seller_raw",
        run_id="r1",
        now=now,
        extra={"dlt_dir": str(env["tmp"] / "dlt"), "tiktok_http": TikTokHttp(API, sleep=lambda s: None)},
    )


def _q(env: dict[str, Any], sql: str) -> list[tuple[Any, ...]]:
    return env["wh"].query(sql)


def test_fr_ing_02_full_sync_and_contract(env: dict[str, Any]) -> None:
    with env["fake"].mock():
        out = sync_tiktok_shop(env["tenant"], env["source"], _ctx(env))
    assert out.tables["tiktok_shop__orders"] == 2
    assert out.tables["tiktok_shop__order_items"] == 3
    assert out.tables["tiktok_shop__settlements"] == 1
    assert out.tables["tiktok_shop__returns"] == 1
    assert out.tables["tiktok_shop__products"] == 2
    assert out.tables["tiktok_shop__daily_totals"] == 90
    for t in ("orders", "order_items", "settlements", "returns", "products", "daily_totals"):
        cols = {
            r[0]
            for r in _q(
                env,
                "select column_name from information_schema.columns where "
                f"table_schema = 't_demo_seller_raw' and table_name = 'tiktok_shop__{t}'",
            )
        }
        assert {"_dx_loaded_at", "_dx_source_account", "_dx_record_hash"} <= cols, t
    totals = dict(
        _q(env, 'select cast(date as varchar), gross_amount from "t_demo_seller_raw"."tiktok_shop__daily_totals"')
    )
    assert int(totals["2026-10-10"]) == 378000
    prods = {
        r[0]: r[1] for r in _q(env, 'select sku_id, category_name from "t_demo_seller_raw"."tiktok_shop__products"')
    }
    assert prods["170000"] == "Serum"


def test_fr_ing_08_refresh_on_expired(env: dict[str, Any]) -> None:
    env["fake"].valid_token = "rotated"
    with env["fake"].mock():
        sync_tiktok_shop(env["tenant"], env["source"], _ctx(env))
    data = json.loads(env["store"].get(SECRET))
    assert env["fake"].refreshes == 1 and data["refresh_token"] == "trt-new"


def test_fr_ing_08_auth_revoked(env: dict[str, Any]) -> None:
    env["fake"].valid_token = "rotated"
    env["fake"].refresh_ok = False
    with env["fake"].mock(), pytest.raises(SourceError) as exc:
        sync_tiktok_shop(env["tenant"], env["source"], _ctx(env))
    assert exc.value.reason == "auth_revoked"


def test_rate_limit(env: dict[str, Any]) -> None:
    env["fake"].rate_limit_next = 2
    with env["fake"].mock():
        out = sync_tiktok_shop(env["tenant"], env["source"], _ctx(env))
    assert out.tables["tiktok_shop__orders"] == 2


def test_fr_ing_07_rescan_open_orders(env: dict[str, Any]) -> None:
    env["fake"].orders[1]["update_time"] = 1791700000  # cũ hơn con trỏ sau lần 1
    with env["fake"].mock():
        sync_tiktok_shop(env["tenant"], env["source"], _ctx(env))
    # Đơn chưa ở trạng thái cuối đổi trạng thái mà nguồn không đổi update_time trong cửa sổ con trỏ.
    env["fake"].orders[1]["status"] = "DELIVERED"
    with env["fake"].mock():
        sync_tiktok_shop(env["tenant"], env["source"], _ctx(env, NOW + timedelta(days=5)))
    assert "/order/202309/orders" in env["fake"].calls
    rows = _q(env, 'select status from "t_demo_seller_raw"."tiktok_shop__orders" where id = \'57261110000002\'')
    assert rows[0][0] == "DELIVERED"


def test_authorize_url() -> None:
    url = authorize_url(APP, "state123")
    assert "service_id=7000" in url and "state=state123" in url
