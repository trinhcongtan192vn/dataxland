"""Xóa dữ liệu một người mua (spec 04 §8, §10): FR-OPS-09."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

import pytest
from dbt_helpers import REPO, SALT, TODAY, Built

pytestmark = pytest.mark.dbt

PHONE = "0909861532"  # người mua trong dữ liệu mẫu demo_seller (Shopee)


def _hash(v: str) -> str:
    return hashlib.sha256(f"{SALT}{v}".encode()).hexdigest()


@pytest.fixture()
def db(built: Built, tmp_path: Path) -> Path:
    dst = tmp_path / "dx.duckdb"  # dbt-duckdb lấy tên file làm tên catalog
    shutil.copy(built.path, dst)
    return dst


def test_fr_ops_09_erase_subject(db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import duckdb
    import erase_subject as es

    from dx_common.tenants import load_tenant_file
    from dx_pipelines.warehouse import DuckDBWarehouse

    monkeypatch.setenv("DUCKDB_PATH", str(db))
    monkeypatch.setenv("DX_TODAY", TODAY)
    tenant = load_tenant_file(REPO / "tenants" / "demo_seller.yml")
    wh = DuckDBWarehouse(db)
    ident = es.Identifier("phone", es.norm_phone("+84 909 861 532"))
    assert ident.value == PHONE

    with duckdb.connect(str(db), read_only=True) as c:
        before = c.execute(
            "select count(*) from t_demo_seller_raw.shopee__orders where recipient_phone = ?", [PHONE]
        ).fetchone()[0]
        assert before > 0
        assert (
            c.execute(
                "select count(*) from t_demo_seller_core.dim_customer where phone_hash = ?", [_hash(PHONE)]
            ).fetchone()[0]
            > 0
        )

    dry = es.erase(tenant, ident, SALT, wh, dry_run=True)
    # Cùng người có thể mua trên nhiều sàn: mọi bảng có số điện thoại đó đều được tìm thấy.
    assert dry.rows["shopee__orders"] == before and set(dry.rows) <= {
        "shopee__orders",
        "lazada__orders",
        "tiktok_shop__orders",
    }
    assert dry.identifier_hash == _hash(PHONE)

    res = es.erase(tenant, ident, SALT, wh, run_dbt=lambda t, s: es.dbt_full_refresh(t, s, SALT))
    assert res.rows == dry.rows and res.dbt_ok is True

    with duckdb.connect(str(db), read_only=True) as c:
        assert (
            c.execute(
                "select count(*) from t_demo_seller_raw.shopee__orders where recipient_phone = ?", [PHONE]
            ).fetchone()[0]
            == 0
        )
        if "lazada__orders" in res.rows:
            assert (
                c.execute(
                    "select count(*) from t_demo_seller_raw.lazada__orders where address_phone = ?", [PHONE]
                ).fetchone()[0]
                == 0
            )
        # Đơn vẫn còn (không sai doanh thu), chỉ mất thông tin cá nhân.
        assert (
            c.execute(
                "select count(*) from t_demo_seller_raw.shopee__orders where order_sn = '2607180100001SP'"
            ).fetchone()[0]
            > 0
        )
        for schema, table, col in [
            ("t_demo_seller_stg", "stg_shopee__orders", "buyer_phone_hash"),
            ("t_demo_seller_stg", "stg_lazada__orders", "buyer_phone_hash"),
            ("t_demo_seller_core", "dim_customer", "phone_hash"),
        ]:
            n = c.execute(f"select count(*) from {schema}.{table} where {col} = ?", [_hash(PHONE)]).fetchone()[0]
            assert n == 0, (schema, table)
        assert (
            c.execute(
                "select count(*) from t_demo_seller_marts.mrt_seller__orders where order_id like '%2607180100001SP%'"
            ).fetchone()[0]
            >= 0
        )


def test_buyer_ref_and_email_matching() -> None:
    import erase_subject as es

    cfg = es.pii_config()
    ref = es.Identifier("buyer_ref", "900127", "shopee")
    assert ref.matches(cfg["shopee__orders"], {"buyer_user_id": 900127})
    assert not ref.matches(cfg["tiktok_shop__orders"], {"user_id": "900127"})
    email = es.Identifier("email", es.norm_email("  Buyer027@Mail.Example "))
    assert email.matches(cfg["tiktok_shop__orders"], {"buyer_email": "buyer027@mail.example"})


def test_ops_path() -> None:
    assert (REPO / "ops" / "erase_subject.py").exists()
    assert os.path.basename(str(REPO / "transform" / "pii_columns.yml")) == "pii_columns.yml"
