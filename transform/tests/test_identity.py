"""Ghép định danh áp vào mô hình chung (spec 10 §7, §9): FR-ID-02 chạy qua dbt thật."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Any

import pytest
from dbt_helpers import REPO, SALT, TODAY, Built, dbt_run

pytestmark = pytest.mark.dbt

PHONE = "0909861532"


class Api:
    def __init__(self) -> None:
        self.matches: dict[str, dict[str, Any]] = {}

    def post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        body = body or {}
        if path.endswith("/matches/keys"):
            return {"pair_keys": list(self.matches), "last_suggest_at": None}
        if path.endswith("/identity/matches"):
            for m in body["matches"]:
                self.matches.setdefault(m["pair_key"], m)
            return {}
        if path.endswith("/identity/approved"):
            return {"pairs": []}
        return {}


def test_fr_id_02_customer_merge_by_phone_hash(built: Built, tmp_path: Path) -> None:
    import duckdb

    from dx_pipelines.warehouse import DuckDBWarehouse
    from identity_worker.worker import run

    db = tmp_path / "dx.duckdb"
    shutil.copy(built.path, db)
    h = hashlib.sha256(f"{SALT}{PHONE}".encode()).hexdigest()
    q = (
        "select source, count(distinct customer_id) from t_demo_seller_core.int_orders "
        "where buyer_phone_hash = ? group by 1"
    )
    with duckdb.connect(str(db), read_only=True) as c:
        before = dict(c.execute(q, [h]).fetchall())
        ids_before = {
            r[0]
            for r in c.execute(
                "select distinct customer_id from t_demo_seller_core.int_orders where buyer_phone_hash = ?", [h]
            ).fetchall()
        }
    assert {"shopee", "lazada"} <= set(before)
    assert len(ids_before) >= 2  # GĐ1: mỗi sàn một khóa người mua

    stats = run(
        "demo_seller",
        "t_demo_seller",
        ["shopee", "tiktok_shop", "lazada"],
        0.7,
        DuckDBWarehouse(db),
        Api(),
        TODAY,
        None,
        "r",
        suggest=False,
        publish_change=False,
    )
    assert stats.customer_rule_pairs > 0 and stats.map_rows > 0
    old = os.environ.get("DUCKDB_PATH")
    os.environ["DUCKDB_PATH"] = str(db)
    try:
        res = dbt_run(db, "demo_seller")
    finally:
        if old is None:
            os.environ.pop("DUCKDB_PATH", None)
        else:
            os.environ["DUCKDB_PATH"] = old
    assert not res.runtime_error, res.stdout_tail[-3000:]
    with duckdb.connect(str(db), read_only=True) as c:
        ids_after = {
            r[0]
            for r in c.execute(
                "select distinct customer_id from t_demo_seller_core.int_orders where buyer_phone_hash = ?", [h]
            ).fetchall()
        }
        n_cust = c.execute("select count(*) from t_demo_seller_core.dim_customer where phone_hash = ?", [h]).fetchone()
    assert len(ids_after) == 1
    assert n_cust[0] == 1


def test_repo_path() -> None:
    assert (REPO / "services" / "identity_worker").exists()
