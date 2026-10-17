"""Kiểm tra sức khỏe chạy qua cùng dbt với khách thật (spec 07 §10): FR-HC-02, NFR-03."""

from __future__ import annotations

from typing import Any

import pytest
from dbt_helpers import REPO, TODAY, Built

pytestmark = pytest.mark.dbt

FILES = {
    "shopee_orders.xlsx": "shopee_orders",
    "shopee_income.xlsx": "shopee_income",
    "tiktok_shop_orders.csv": "tiktok_shop_orders",
    "tiktok_shop_settlement.csv": "tiktok_shop_settlement",
    "lazada_orders.xlsx": "lazada_orders",
    "lazada_transactions.csv": "lazada_transactions",
    "meta_ads.csv": "meta_ads",
    "product_costs.xlsx": "product_costs",
}
CHECK = "01testhc"


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def post(self, path: str, body: Any = None) -> dict[str, Any]:
        self.calls.append((path, body))
        if path.endswith("/start"):
            files = [
                {
                    "id": f"f{i}",
                    "declared_kind": k,
                    "filename": n,
                    "path": str(REPO / "transform" / "samples" / "files" / n),
                }
                for i, (n, k) in enumerate(FILES.items())
            ]
            return {"files": files, "salt": "hc-test-salt", "expires_at": "2026-10-30T00:00:00Z"}
        return {}


class FakeCube:
    def refresh(self, *a: Any) -> None:
        pass


@pytest.fixture(scope="module")
def hc(built: Built, tmp_path_factory: pytest.TempPathFactory) -> FakeApi:
    import os

    from dx_pipelines.jobs.healthcheck import run_healthcheck
    from dx_pipelines.warehouse import DuckDBWarehouse

    old = {k: os.environ.get(k) for k in ("DUCKDB_PATH", "DX_TODAY")}
    os.environ["DUCKDB_PATH"] = str(built.path)
    os.environ["DX_TODAY"] = TODAY
    try:
        api = FakeApi()
        res = run_healthcheck(CHECK, api=api, cube=FakeCube(), warehouse=DuckDBWarehouse(built.path))
        assert res["status"] == "ready_for_review", res.get("log", res)
        return api
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_fr_hc_02_same_metrics_code(hc: FakeApi, built: Built) -> None:
    """Doanh thu thực nhận của lượt kiểm tra từ file mẫu bằng của `demo_seller` cùng kỳ (≤ 1%)."""
    q = (
        "select platform, sum(net_revenue_vnd), count(*) from {s}.mrt_seller__orders "
        "where order_date between '2026-09-16' and '2026-10-10' group by 1"
    )
    with built.con() as c:
        hc_rows = {p: (float(v), n) for p, v, n in c.execute(q.format(s=f"hc_{CHECK}_marts")).fetchall()}
        demo = {p: (float(v), n) for p, v, n in c.execute(q.format(s="t_demo_seller_marts")).fetchall()}
    assert set(hc_rows) == set(demo) == {"shopee", "tiktok_shop", "lazada"}
    for p in demo:
        assert hc_rows[p][1] == demo[p][1], p
        assert abs(hc_rows[p][0] - demo[p][0]) <= 0.01 * abs(demo[p][0]), (p, hc_rows[p], demo[p])


def test_nfr_03_file_pii_dropped(hc: FakeApi, built: Built) -> None:
    with built.con() as c:
        cols = c.execute(
            "select table_name, column_name from information_schema.columns where table_schema = ?",
            [f"hc_{CHECK}_raw"],
        ).fetchall()
        assert cols
        bad = [
            (t, col)
            for t, col in cols
            if any(x in col.lower() for x in ("phone", "address", "recipient", "customer_name", "email"))
        ]
        assert bad == []
        # Mã người mua chỉ còn dạng băm 64 ký tự hex.
        refs = c.execute(f"select distinct buyer_ref_hash from hc_{CHECK}_raw.shopee_file__orders limit 5").fetchall()
        assert refs and all(r[0] is None or (len(r[0]) == 64 and int(r[0], 16) >= 0) for r in refs)


def test_rejected_and_ranges_reported(hc: FakeApi) -> None:
    files = next(b for p, b in hc.calls if p.endswith("/files"))["files"]
    assert all(f["status"] == "loaded" for f in files)
    shopee = next(f for f in files if f["detected_kind"] == "shopee_orders")
    assert (shopee["date_from"], shopee["date_to"]) == ("2026-07-18", "2026-10-15")
    build = next(b for p, b in hc.calls if p.endswith("/build"))
    assert build["mapping_issues"] == []


def test_raw_contract_columns(hc: FakeApi, built: Built) -> None:
    with built.con() as c:
        tables = {
            r[0]
            for r in c.execute(
                "select table_name from information_schema.tables where table_schema = ?", [f"hc_{CHECK}_raw"]
            ).fetchall()
        }
        assert {"shopee_file__orders", "shopee_file__returns", "portal_file__product_costs"} <= tables
        for t in tables - {"dx__status_map_override"}:
            cols = {
                r[0]
                for r in c.execute(
                    "select column_name from information_schema.columns where table_schema = ? and table_name = ?",
                    [f"hc_{CHECK}_raw", t],
                ).fetchall()
            }
            assert {"_dx_loaded_at", "_dx_source_account", "_dx_record_hash"} <= cols, t
