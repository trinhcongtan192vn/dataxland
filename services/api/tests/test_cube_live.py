"""Test với Cube thật (spec 03 §11), đánh dấu `cube`. Bỏ qua khi không gọi được `CUBE_API_URL`.

Chuẩn bị: `make dbt-build TENANT=demo_seller` (`--fixed-samples`) và `TENANT=demo_agency`, rồi bật Cube với cùng
`CUBE_API_SECRET` (`test-cube-secret`) và kho DuckDB đó.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
import yaml

from tests.conftest import REPO

CUBE = os.environ.get("DX_TEST_CUBE_URL", "http://localhost:4000")
SECRET = os.environ["CUBE_API_SECRET"]


def _up() -> bool:
    try:
        return httpx.get(f"{CUBE}/readyz", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = [pytest.mark.cube, pytest.mark.skipif(not _up(), reason="Cube không chạy")]

QUERY = {"measures": ["mrt_seller__orders.net_revenue"], "limit": 1}


def _token(**claims: Any) -> str:
    now = int(time.time())
    return jwt.encode({"iat": now, "exp": now + 300, **claims}, SECRET, algorithm="HS256")


def test_fr_met_05_cube_rejects_missing_tenant() -> None:
    for claims in (
        {"dataset_prefix": "t_demo_seller"},
        {"tenant_id": "", "dataset_prefix": "t_demo_seller"},
        {"tenant_id": "demo_seller", "dataset_prefix": "t_demo_agency"},
    ):
        r = httpx.post(
            f"{CUBE}/cubejs-api/v1/load", json={"query": QUERY}, headers={"Authorization": _token(**claims)}, timeout=30
        )
        assert r.status_code == 403, (claims, r.text)
    r = httpx.post(f"{CUBE}/cubejs-api/v1/load", json={"query": QUERY}, timeout=30)
    assert r.status_code == 403


def _sql(tenant: str) -> str:
    q = {"measures": ["mrt_common__ad_daily.ad_spend"], "limit": 1}
    r = httpx.post(
        f"{CUBE}/cubejs-api/v1/sql",
        json={"query": q},
        headers={"Authorization": _token(tenant_id=tenant, dataset_prefix=f"t_{tenant}")},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    return str(r.json()["sql"]["sql"][0])


def test_fr_met_05_cube_tenant_isolation() -> None:
    s, a = _sql("demo_seller"), _sql("demo_agency")
    assert "t_demo_seller_marts" in s and "t_demo_agency" not in s
    assert "t_demo_agency_marts" in a and "t_demo_seller" not in a


@pytest.fixture()
def live_cube(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.metrics.cube_client import CubeClient, set_cube

    monkeypatch.setenv("DX_TODAY", "2026-10-16")
    set_cube(CubeClient(CUBE))
    yield
    set_cube(None)


@pytest.mark.parametrize("pack", ["seller", "agency"])
def test_key_numbers_seller_agency(live_cube: None, pack: str) -> None:
    from datetime import date

    from app.auth.context import AuthContext
    from app.metrics.key_numbers import key_numbers
    from dx_common.tenants import load_tenant_file

    exp = yaml.safe_load((REPO / "semantic" / "tests" / "expected" / f"{pack}.yml").read_text(encoding="utf-8"))
    cfg = load_tenant_file(Path(REPO / "tenants" / f"{exp['tenant']}.yml"))
    ctx = AuthContext(
        tenant_id=cfg.tenant_id, role="owner", pack=cfg.pack, dataset_prefix=cfg.dataset_prefix, tenant=cfg
    )
    out = key_numbers(ctx, exp["period"], today=date(2026, 10, 16))
    assert (out["period"]["from"], out["period"]["to"]) == (exp["from"], exp["to"])
    got = {n["key"]: n["value"] for n in out["numbers"]}
    for k, v in exp["numbers"].items():
        assert got[k] == pytest.approx(v, rel=1e-6), k
