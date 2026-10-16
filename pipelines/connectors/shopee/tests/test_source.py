"""Connector Shopee với API giả lập (spec 01 §11): phân trang, làm mới token, 429, mất quyền, hợp đồng raw."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from connectors.base import SourceError, SyncContext
from connectors.shopee.client import ShopeeHttp, authorize_url, sign
from connectors.shopee.source import sync_shopee
from connectors.shopee.tests.fake_shopee import BASE, FakeShopee
from dx_common.secrets import LocalFileSecretStore, set_secret_store
from dx_common.tenants import load_tenant_file
from dx_pipelines.warehouse import DuckDBWarehouse

REPO = Path(__file__).resolve().parents[4]
NOW = datetime(2026, 10, 16, 0, 0, tzinfo=UTC)
SECRET = "dx-demo_seller-shopee-100001"


def make_env(tmp_path: Path) -> Iterator[dict[str, Any]]:
    """Secret, cấu hình khách, kho DuckDB tạm và Shopee giả lập; dùng chung cho test FR-ING-07."""
    store = LocalFileSecretStore(tmp_path / "secrets")
    store.put("dx-shopee-app", json.dumps({"partner_id": 2001234, "partner_key": "test-partner-key", "api_base": BASE}))
    store.put(
        SECRET,
        json.dumps(
            {"shop_id": "100001", "access_token": "at-1", "refresh_token": "rt-1", "expires_at": "2026-10-16T03:00:00Z"}
        ),
    )
    set_secret_store(store)
    tenant = load_tenant_file(REPO / "tenants" / "demo_seller.yml")
    source = next(s for s in tenant.sources if s.type == "shopee").model_copy(update={"secret_ref": SECRET})
    wh = DuckDBWarehouse(tmp_path / "wh.duckdb")
    fake = FakeShopee()
    yield {"tenant": tenant, "source": source, "wh": wh, "fake": fake, "store": store, "tmp": tmp_path}
    set_secret_store(None)


@pytest.fixture()
def env(tmp_path: Path) -> Iterator[dict[str, Any]]:
    yield from make_env(tmp_path)


def _ctx(env: dict[str, Any], now: datetime = NOW) -> SyncContext:
    http = ShopeeHttp(BASE, sleep=lambda s: None)
    return SyncContext(
        warehouse=env["wh"],
        raw_dataset="t_demo_seller_raw",
        run_id="r1",
        now=now,
        extra={"dlt_dir": str(env["tmp"] / "dlt"), "shopee_http": http},
    )


def _rows(wh: DuckDBWarehouse, table: str, cols: str = "*") -> list[tuple[Any, ...]]:
    return wh.query(f'select {cols} from "t_demo_seller_raw"."{table}"')


def test_fr_ing_01_full_sync_and_contract(env: dict[str, Any]) -> None:
    with env["fake"].mock():
        out = sync_shopee(env["tenant"], env["source"], _ctx(env))
    wh = env["wh"]
    assert out.tables["shopee__orders"] == 2
    assert out.tables["shopee__order_items"] == 2
    assert out.tables["shopee__escrow"] == 1  # chỉ đơn COMPLETED
    assert out.tables["shopee__returns"] == 1
    assert out.tables["shopee__products"] == 2
    assert out.tables["shopee__daily_totals"] == 90
    tables = set(wh.list_tables("t_demo_seller_raw"))
    for t in ("orders", "order_items", "escrow", "returns", "products", "daily_totals"):
        assert f"shopee__{t}" in tables
        cols = {
            r[0]
            for r in wh.query(
                "select column_name from information_schema.columns where table_schema = 't_demo_seller_raw' "
                f"and table_name = 'shopee__{t}'"
            )
        }
        assert {"_dx_loaded_at", "_dx_source_account", "_dx_record_hash"} <= cols, t
    o = dict(_rows(wh, "shopee__orders", "order_sn, order_original_amount"))
    assert int(o["2610100100001SP"]) == 578000
    v = _rows(wh, "shopee__orders", "shopee_voucher")
    assert any(int(x[0] or 0) == 15000 for x in v)
    totals = dict(_rows(wh, "shopee__daily_totals", "cast(date as varchar), order_count"))
    assert totals["2026-10-10"] == 1 and totals["2026-10-11"] == 1
    assert {r[0] for r in _rows(wh, "shopee__orders", "_dx_source_account")} == {"100001"}


def test_pagination_one_order_per_page(env: dict[str, Any]) -> None:
    with env["fake"].mock():
        sync_shopee(env["tenant"], env["source"], _ctx(env))
    # Hai đơn trong cùng cửa sổ update_time → ít nhất hai trang get_order_list cho cửa sổ đó.
    assert env["fake"].calls.count("/api/v2/order/get_order_detail") == 1
    assert env["fake"].calls.count("/api/v2/order/get_order_list") > 13 + 90


def test_fr_ing_08_token_refreshed_before_run(env: dict[str, Any]) -> None:
    with env["fake"].mock():
        sync_shopee(env["tenant"], env["source"], _ctx(env, NOW + timedelta(hours=2, minutes=45)))
    data = json.loads(env["store"].get(SECRET))
    assert env["fake"].refreshes == 1
    assert data["access_token"] == "at-2" and data["refresh_token"] == "rt-new"
    assert data["expires_at"] == "2026-10-16T06:45:00Z"


def test_fr_ing_08_refresh_on_expired_error(env: dict[str, Any]) -> None:
    env["fake"].valid_token = "at-server-rotated"  # nguồn coi token hiện tại đã hết hạn
    with env["fake"].mock():
        out = sync_shopee(env["tenant"], env["source"], _ctx(env))
    assert env["fake"].refreshes == 1
    assert out.tables["shopee__orders"] == 2


def test_fr_ing_08_auth_revoked(env: dict[str, Any]) -> None:
    env["fake"].valid_token = "other"
    env["fake"].refresh_ok = False
    with env["fake"].mock(), pytest.raises(SourceError) as exc:
        sync_shopee(env["tenant"], env["source"], _ctx(env))
    assert exc.value.reason == "auth_revoked"


def test_rate_limit_retries_then_succeeds(env: dict[str, Any]) -> None:
    env["fake"].rate_limit_next = 3
    with env["fake"].mock():
        out = sync_shopee(env["tenant"], env["source"], _ctx(env))
    assert out.tables["shopee__orders"] == 2


def test_rate_limit_gives_up_after_five(env: dict[str, Any]) -> None:
    env["fake"].rate_limit_next = 100
    with env["fake"].mock(), pytest.raises(SourceError) as exc:
        sync_shopee(env["tenant"], env["source"], _ctx(env))
    assert exc.value.reason == "rate_limited"


def test_incremental_cursor_second_run(env: dict[str, Any]) -> None:
    with env["fake"].mock():
        sync_shopee(env["tenant"], env["source"], _ctx(env))
    env["fake"].calls.clear()
    with env["fake"].mock():
        out = sync_shopee(env["tenant"], env["source"], _ctx(env, NOW + timedelta(hours=6)))
    # Lần sau chỉ quét từ con trỏ (một cửa sổ) và lấy lại 30 ngày tổng theo ngày.
    lists = env["fake"].calls.count("/api/v2/order/get_order_list")
    assert lists < 40
    # Đơn SHIPPED chưa ở trạng thái cuối nên vẫn được lấy lại (FR-ING-07).
    assert out.tables["shopee__orders"] >= 1


def test_sign_and_authorize_url() -> None:
    import hashlib
    import hmac

    assert sign("k", "base") == hmac.new(b"k", b"base", hashlib.sha256).hexdigest()
    url = authorize_url({"partner_id": 1, "partner_key": "k", "api_base": BASE}, "https://api.test/cb", ts=100)
    assert url.startswith(f"{BASE}/api/v2/shop/auth_partner?")
    assert "redirect=https%3A%2F%2Fapi.test%2Fcb" in url
    assert f"sign={sign('k', '1/api/v2/shop/auth_partner100')}" in url
