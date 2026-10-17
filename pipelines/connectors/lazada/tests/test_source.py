"""Connector Lazada với API giả lập (spec 01 §11, FR-ING-03)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from connectors.base import SourceError, SyncContext
from connectors.lazada.client import LazadaHttp
from connectors.lazada.source import sync_lazada
from connectors.lazada.tests.fake_lazada import API, APP, FakeLazada
from dx_common.secrets import LocalFileSecretStore, set_secret_store
from dx_common.tenants import load_tenant_file
from dx_pipelines.warehouse import DuckDBWarehouse

REPO = Path(__file__).resolve().parents[4]
NOW = datetime(2026, 10, 16, 0, 0, tzinfo=UTC)
SECRET = "dx-demo_seller-lazada-300001"


@pytest.fixture()
def env(tmp_path: Path) -> Iterator[dict[str, Any]]:
    store = LocalFileSecretStore(tmp_path / "secrets")
    store.put("dx-lazada-app", json.dumps(APP))
    store.put(
        SECRET,
        json.dumps(
            {
                "seller_id": "300001",
                "access_token": "lz-1",
                "refresh_token": "lzr-1",
                "expires_at": "2026-10-20T00:00:00Z",
            }
        ),
    )
    set_secret_store(store)
    tenant = load_tenant_file(REPO / "tenants" / "demo_seller.yml")
    source = next(s for s in tenant.sources if s.type == "lazada").model_copy(update={"secret_ref": SECRET})
    yield {
        "tenant": tenant,
        "source": source,
        "wh": DuckDBWarehouse(tmp_path / "wh.duckdb"),
        "fake": FakeLazada(),
        "store": store,
        "tmp": tmp_path,
    }
    set_secret_store(None)


def _ctx(env: dict[str, Any], now: datetime = NOW) -> SyncContext:
    return SyncContext(
        warehouse=env["wh"],
        raw_dataset="t_demo_seller_raw",
        run_id="r",
        now=now,
        extra={"dlt_dir": str(env["tmp"] / "dlt"), "lazada_http": LazadaHttp(API, sleep=lambda s: None)},
    )


def _q(env: dict[str, Any], sql: str) -> list[tuple[Any, ...]]:
    return env["wh"].query(sql)


def test_fr_ing_03_full_sync_and_contract(env: dict[str, Any]) -> None:
    with env["fake"].mock():
        out = sync_lazada(env["tenant"], env["source"], _ctx(env))
    assert out.tables["lazada__orders"] == 2
    assert out.tables["lazada__order_items"] == 3
    assert out.tables["lazada__transactions"] == 2
    assert out.tables["lazada__returns"] == 1
    assert out.tables["lazada__products"] == 1
    assert out.tables["lazada__daily_totals"] == 90
    for t in ("orders", "order_items", "transactions", "returns", "products", "daily_totals"):
        cols = {
            r[0]
            for r in _q(
                env,
                "select column_name from information_schema.columns where "
                f"table_schema = 't_demo_seller_raw' and table_name = 'lazada__{t}'",
            )
        }
        assert {"_dx_loaded_at", "_dx_source_account", "_dx_record_hash"} <= cols, t
    rows = dict(_q(env, 'select order_id, statuses from "t_demo_seller_raw"."lazada__orders"'))
    assert rows["826101000001"] == "confirmed"
    phone = _q(
        env,
        'select address_phone, address_full from "t_demo_seller_raw"."lazada__orders" where order_id = \'826101000001\'',
    )
    assert phone[0] == ("0900000011", "1 Đường A, Hà Nội")
    totals = dict(_q(env, 'select cast(date as varchar), gross_amount from "t_demo_seller_raw"."lazada__daily_totals"'))
    assert int(totals["2026-10-10"]) == 538000


def test_fr_ing_08_refresh_and_revoked(env: dict[str, Any]) -> None:
    env["fake"].valid_token = "rotated"
    with env["fake"].mock():
        sync_lazada(env["tenant"], env["source"], _ctx(env))
    assert env["fake"].refreshes == 1 and json.loads(env["store"].get(SECRET))["refresh_token"] == "lzr-new"
    env["fake"].valid_token = "rotated-again"
    env["fake"].refresh_ok = False
    with env["fake"].mock(), pytest.raises(SourceError) as exc:
        sync_lazada(env["tenant"], env["source"], _ctx(env, NOW + timedelta(hours=6)))
    assert exc.value.reason == "auth_revoked"


def test_rate_limit_retry(env: dict[str, Any]) -> None:
    env["fake"].rate_limit_next = 3
    with env["fake"].mock():
        out = sync_lazada(env["tenant"], env["source"], _ctx(env))
    assert out.tables["lazada__orders"] == 2


def test_fr_ing_07_rescan_open_orders(env: dict[str, Any]) -> None:
    with env["fake"].mock():
        sync_lazada(env["tenant"], env["source"], _ctx(env))
    env["fake"].orders[1]["statuses"] = ["delivered"]  # đơn mở đổi trạng thái, update_time cũ hơn con trỏ
    env["fake"].orders[1]["updated_at"] = "2026-10-11 12:00:00 +0700"
    with env["fake"].mock():
        sync_lazada(env["tenant"], env["source"], _ctx(env, NOW + timedelta(days=2)))
    assert "/order/get" in env["fake"].calls
    rows = _q(env, 'select statuses from "t_demo_seller_raw"."lazada__orders" where order_id = \'826101100002\'')
    assert rows[0][0] == "delivered"
