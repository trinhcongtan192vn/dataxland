"""Tiêu chí hoàn thành spec 02 §9 và kiểm thử tách biệt khách phần dbt (spec 00 §9.3)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from dbt_helpers import REPO, Built, dbt_run, seed

pytestmark = pytest.mark.dbt

PHONE_RE = re.compile(r"(?<![0-9A-Za-z])(?:\+?84|0)\d{9,10}(?![0-9A-Za-z])")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PII_NAMES = ("phone", "email", "address", "buyer_name", "recipient", "customer_first_name")


def _results(res: Any) -> dict[str, str]:
    return {r["unique_id"]: r["status"] for r in res.run_results.get("results", [])}


def test_build_green_for_both_tenants(built: Built) -> None:
    con = built.con()
    for t in ("t_demo_seller_marts", "t_demo_agency_marts"):
        tables = {r[0] for r in con.execute(
            "select table_name from information_schema.tables where table_schema = ?", [t]).fetchall()}
        assert "mrt_common__data_status" in tables and "mrt_common__ad_daily" in tables
        assert not any(x.endswith("__staging") for x in tables), "marts phải được hoán đổi sau khi test qua"
    assert "mrt_seller__orders" in {r[0] for r in con.execute(
        "select table_name from information_schema.tables where table_schema = 't_demo_seller_marts'").fetchall()}


def test_nfr_03_no_raw_pii_in_core_and_marts(built: Built) -> None:
    con = built.con()
    cols = con.execute(
        "select table_schema, table_name, column_name, data_type from information_schema.columns "
        "where table_schema like 't_demo_%_core' or table_schema like 't_demo_%_marts'").fetchall()
    for schema, table, col, _ in cols:
        low = col.lower()
        if low.endswith("_hash"):
            continue
        assert not any(n in low for n in PII_NAMES), f"{schema}.{table}.{col}"
    for schema, table, col, typ in cols:
        if "VARCHAR" not in typ.upper():
            continue
        vals = [r[0] for r in con.execute(f'select distinct "{col}" from "{schema}"."{table}" limit 2000').fetchall()]
        for v in vals:
            if v is None:
                continue
            assert not PHONE_RE.search(str(v)), f"số điện thoại gốc trong {schema}.{table}.{col}"
            assert not EMAIL_RE.search(str(v)), f"email gốc trong {schema}.{table}.{col}"


def test_isolation_no_cross_tenant_reference(built: Built) -> None:
    """Không model dbt nào tham chiếu dataset của khách khác: quét manifest sau dbt build (spec 00 §9.3)."""
    for tenant, other in (("demo_seller", "demo_agency"), ("demo_agency", "demo_seller")):
        manifest = json.loads((built.tmp / f"target_{tenant}_t" / "manifest.json").read_text(encoding="utf-8"))
        for node in manifest["nodes"].values():
            if node.get("resource_type") not in ("model", "test", "seed"):
                continue
            code = (node.get("compiled_code") or "") + str(node.get("schema"))
            assert f"t_{other}_" not in code, node["unique_id"]
        for src in manifest["sources"].values():
            assert f"t_{other}_" not in src["schema"], src["unique_id"]


def test_fr_mod_03_usd_converted(built: Built) -> None:
    con = built.con()
    row = con.execute(
        "select currency, gross_amount_original, gross_amount_vnd from t_demo_agency_core.fct_order "
        "where source = 'amazon_seller' limit 1").fetchone()
    assert row[0] == "USD" and float(row[2]) > float(row[1]) * 20000
    # Ngày cuối tuần không có tỷ giá dùng tỷ giá ngày làm việc gần nhất trước đó.
    sat, fri = con.execute(
        "select (select rate_vnd from t_demo_agency_stg.stg_fx__rates_daily where date = '2026-10-10'),"
        " (select rate_vnd from t_demo_agency_stg.stg_fx__rates_daily where date = '2026-10-09')").fetchone()
    assert sat == fri


def test_fr_inp_03_missing_cogs_counted(built: Built) -> None:
    row = built.con().execute(
        "select missing_cogs_sku_count, missing_cogs_revenue_vnd from t_demo_seller_marts.mrt_common__data_status").fetchone()
    assert row[0] == 1 and float(row[1]) > 0


def test_fr_mod_05_sum_preserved_all_modes(built: Built) -> None:
    for mode in ("by_revenue", "by_order", "none"):
        res = dbt_run(built.path, "demo_seller", extra_vars={"cost_allocation": mode},
                      select=["fct_cost_allocated"], target_name=f"alloc_{mode}", swap=False)
        statuses = _results(res)
        sp = [k for k in statuses if "sum_preserved" in k]
        assert sp and all(statuses[k] == "pass" for k in sp), (mode, statuses)
    dbt_run(built.path, "demo_seller", select=["fct_cost_allocated"], target_name="alloc_reset", swap=False)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def test_fr_mod_01_unknown_status_blocks_until_override(scratch_samples: Path, tmp_path: Path) -> None:
    """Trạng thái lạ làm test ánh xạ lỗi; thêm vào file ghi đè thì qua (FR-MOD-01, FR-MOD-04)."""
    p = scratch_samples / "lazada" / "orders.jsonl"
    rows = _jsonl(p)
    rows[0] = {**rows[0], "statuses": "WEIRD_STATUS"}
    _write_jsonl(p, rows)
    db = tmp_path / "dx.duckdb"
    seed(db, scratch_samples)
    res = dbt_run(db, "demo_seller", select=["+stg_lazada__orders"], target_name="weird", swap=False)
    failed = [k for k, v in _results(res).items() if k.startswith("test.") and v == "fail"]
    # Trạng thái chưa ánh xạ thành null → test trên cột `status` lỗi, mức chặn (spec 02 §3.3).
    assert any("stg_lazada__orders_status" in k for k in failed), failed

    override = REPO / "tenants" / "overrides" / "demo_seller_status_map.csv"
    original = override.read_text(encoding="utf-8")
    try:
        override.write_text(original.rstrip("\n") + "\nlazada,WEIRD_STATUS,pending\n", encoding="utf-8")
        res = dbt_run(db, "demo_seller", select=["+stg_lazada__orders"], target_name="weird2", swap=False)
        failed = [k for k, v in _results(res).items() if k.startswith("test.") and v == "fail"]
        assert failed == [], failed
    finally:
        override.write_text(original, encoding="utf-8")


def test_fr_dq_02_reconcile_detects_2pct_gap(scratch_samples: Path, tmp_path: Path) -> None:
    p = scratch_samples / "shopee" / "daily_totals.jsonl"
    rows = _jsonl(p)
    target_day = "2026-10-12"
    for r in rows:
        if r["date"] == target_day and r["_dx_source_account"] == "100001":
            r["gross_amount"] = int(r["gross_amount"] * 1.02)
    _write_jsonl(p, rows)
    db = tmp_path / "dx.duckdb"
    seed(db, scratch_samples)
    res = dbt_run(db, "demo_seller", select=["+fct_order", "+stg_shopee__daily_totals"], target_name="recon", swap=False,
                  exclude=["resource_type:unit_test"])
    st = _results(res)
    rec = [k for k in st if "reconcile_daily_totals_shopee" in k]
    assert rec and st[rec[0]] == "fail"
    import duckdb

    con = duckdb.connect(str(db), read_only=True)
    out = con.execute("select source, cast(date as varchar), metric, diff_pct from "
                      "t_demo_seller_audit.reconcile_daily_totals_shopee").fetchall()
    assert ("shopee", target_day, "gross_amount") in [(a, b, c) for a, b, c, _ in out]
    gaps = [float(d) for a, b, c, d in out if b == target_day and c == "gross_amount"]
    assert gaps and 1.5 < gaps[0] < 2.5
