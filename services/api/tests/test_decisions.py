"""Nhật ký quyết định (spec 06 §7): FR-DEC-01, FR-DEC-02."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from tests.conftest import INTERNAL, auth
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


BODY = {
    "decided_on": "2026-10-01",
    "title": "Tăng giá combo quà tặng 10%",
    "decided_by": "Chủ shop",
    "metric": "net_revenue",
    "baseline_window": "last_7_days",
    "remeasure_on": "2026-10-10",
    "dimension_filter": [{"dimension": "platform", "op": "eq", "value": "shopee"}],
}


def test_fr_dec_01_baseline_auto_filled(client: Any, cube: FakeCube) -> None:
    r = client.post("/v1/decisions", json=BODY, headers=auth("owner_seller", "demo_seller"))
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["baseline_value"] == 10_000_000
    assert d["metric_version"] and d["metric_name_vi"] == "Doanh thu thực nhận"
    assert (d["baseline_from"], d["baseline_to"]) == ("2026-09-24", "2026-09-30")
    q = next(c[2] for c in cube.calls if "measures" in c[2])
    assert q["timeDimensions"][0]["dateRange"] == ["2026-09-24", "2026-09-30"]
    assert q["filters"][0]["values"] == ["shopee"]
    assert client.get("/v1/decisions", headers=auth("member_seller", "demo_seller")).json()[0]["id"] == d["id"]


def test_member_cannot_write_and_metric_scope_applies(client: Any, cube: FakeCube) -> None:
    assert client.post("/v1/decisions", json=BODY, headers=auth("member_seller", "demo_seller")).status_code == 403
    bad = dict(BODY, metric="net_profit_after_fees")
    assert client.post("/v1/decisions", json=bad, headers=auth("owner_agency", "demo_agency")).status_code == 403


def test_fr_dec_02_remind_and_measure(client: Any, cube: FakeCube, session: Any) -> None:
    d = client.post("/v1/decisions", json=BODY, headers=auth("owner_seller", "demo_seller")).json()
    r = client.post("/v1/internal/decisions/remind", headers=INTERNAL)
    assert r.json()["decision_ids"] == [d["id"]]
    assert client.post("/v1/internal/decisions/remind", headers=INTERNAL).json()["reminded"] == 0
    from sqlalchemy import text

    n = session.execute(text("select count(*) from events where type = 'decision.remeasure_due'")).scalar()
    assert n == 1
    cube.values["net_revenue"] = 12_000_000
    m = client.post(f"/v1/decisions/{d['id']}/measure", headers=auth("owner_seller", "demo_seller"))
    assert m.status_code == 200, m.text
    assert m.json()["after_value"] == 12_000_000
    assert (m.json()["after_from"], m.json()["after_to"]) == ("2026-10-01", "2026-10-07")
    u = client.put(
        f"/v1/decisions/{d['id']}",
        json={"conclusion": "achieved", "conclusion_md": "Doanh thu tăng 20%"},
        headers=auth("owner_seller", "demo_seller"),
    )
    assert u.json()["conclusion"] == "achieved" and u.json()["due"] is False


def test_measure_too_early(client: Any, cube: FakeCube) -> None:
    body = dict(BODY, decided_on="2026-10-14", remeasure_on="2026-10-21")
    d = client.post("/v1/decisions", json=body, headers=auth("owner_seller", "demo_seller")).json()
    r = client.post(f"/v1/decisions/{d['id']}/measure", headers=auth("owner_seller", "demo_seller"))
    assert r.status_code == 409 and r.json()["code"] == "TOO_EARLY"


def test_other_tenant_cannot_read(client: Any, cube: FakeCube) -> None:
    d = client.post("/v1/decisions", json=BODY, headers=auth("owner_seller", "demo_seller")).json()
    r = client.get(f"/v1/decisions/{d['id']}", headers=auth("owner_agency", "demo_agency"))
    assert r.status_code == 404
