"""Trang agency (spec 06 §8): FR-AGY-01, FR-AGY-02, FR-AUTH-04."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from tests.conftest import auth
from tests.test_metrics import FakeCube


@pytest.fixture()
def cube(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeCube]:
    from app.metrics.cube_client import set_cube

    monkeypatch.setenv("DX_TODAY", "2026-10-16")
    monkeypatch.setenv("DX_NOW", "2026-10-16T03:00:00Z")
    fake = FakeCube()
    set_cube(fake)
    yield fake
    set_cube(None)


def test_fr_agy_01_partner_sees_granted_tenants(client: Any, cube: FakeCube) -> None:
    r = client.get("/v1/partner/tenants", headers=auth("partner"))
    assert r.status_code == 200, r.text
    rows = r.json()
    assert [x["tenant_id"] for x in rows] == ["demo_agency"]
    assert rows[0]["ad_spend_mtd"] == 3_000_000 and rows[0]["error"] is None
    # Mỗi truy vấn chỉ đọc đúng một khách.
    assert {t for t, _, _ in cube.calls} == {"demo_agency"}


def test_fr_agy_02_revoke_removes_tenant(client: Any, cube: FakeCube) -> None:
    grants = client.get("/v1/partners/grants", headers=auth("owner_agency", "demo_agency")).json()
    gid = next(g["id"] for g in grants if g["partner_id"] == "demo_partner")
    assert client.delete(f"/v1/partners/grants/{gid}", headers=auth("owner_agency", "demo_agency")).status_code == 204
    assert client.get("/v1/partner/tenants", headers=auth("partner")).json() == []
    direct = client.post("/v1/metrics/query", json={"metrics": ["ad_spend"]}, headers=auth("partner", "demo_agency"))
    assert direct.status_code == 403


def test_non_partner_forbidden(client: Any) -> None:
    assert client.get("/v1/partner/tenants", headers=auth("owner_seller")).status_code == 403
