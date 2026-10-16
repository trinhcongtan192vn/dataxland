"""Báo cáo tuần (spec 06 §4): FR-REP-01, FR-REP-04..07."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import select

from tests.conftest import INTERNAL, FakeChannel, auth
from tests.test_metrics import FakeCube
from tests.test_notify import _run


@pytest.fixture()
def cube(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeCube]:
    from app.metrics.cube_client import set_cube

    monkeypatch.setenv("DX_TODAY", "2026-10-16")
    monkeypatch.setenv("DX_NOW", "2026-10-16T03:00:00Z")
    fake = FakeCube()
    set_cube(fake)
    yield fake
    set_cube(None)


@pytest.fixture()
def drained(session: Any, channels: dict[str, FakeChannel]) -> dict[str, FakeChannel]:
    from app.db.models import Notification

    _run(session)
    session.query(Notification).delete()
    session.commit()
    for c in channels.values():
        c.sent.clear()
    return channels


def _build(client: Any, tenant: str = "demo_seller") -> dict[str, Any]:
    r = client.post("/v1/internal/reports/build", json={"tenant_id": tenant, "run_id": "run-1"}, headers=INTERNAL)
    assert r.status_code == 200, r.text
    return dict(r.json())


def test_fr_rep_01_build_draft_snapshot(client: Any, cube: FakeCube, session: Any) -> None:
    from app.db.models import Report

    res = _build(client)
    assert res["status"] == "draft"
    rep = session.get(Report, res["report_id"])
    assert (str(rep.period_start), str(rep.period_end)) == ("2026-10-05", "2026-10-11")
    snap = rep.snapshot
    assert [n["key"] for n in snap["key_numbers"]["numbers"]] == [
        "net_revenue",
        "net_profit_after_fees",
        "net_profit_change_pct",
    ]
    assert snap["pnl"]["net_revenue"] == 10_000_000 and "compare" in snap["pnl"]
    assert snap["metrics"]["net_revenue"]["version"] and snap["run_id"] == "run-1"
    assert len(snap["top_skus"]) <= 5 and "bottom_skus" in snap and "rates" in snap
    assert any(w["code"] == "MISSING_COGS" for w in snap["warnings"])
    # Khách không thấy bản nháp.
    assert client.get("/v1/reports", headers=auth("owner_seller", "demo_seller")).json() == []
    assert client.get(f"/v1/reports/{rep.id}", headers=auth("owner_seller", "demo_seller")).status_code == 404


def test_fr_rep_03_agency_snapshot(client: Any, cube: FakeCube, session: Any) -> None:
    from app.db.models import Report

    res = _build(client, "demo_agency")
    snap = session.get(Report, res["report_id"]).snapshot
    assert {"spend_by_platform", "budget", "roas", "flags", "campaigns_attention", "amazon"} <= set(snap)
    assert snap["budget"]["month"] == "2026-10"


def test_fr_rep_04_insight_required_then_approve(
    client: Any, cube: FakeCube, session: Any, drained: dict[str, FakeChannel]
) -> None:
    rid = _build(client)["report_id"]
    lead = auth("data_lead")
    assert client.post(f"/v1/reports/{rid}/approve", headers=lead).json()["code"] == "INSIGHT_REQUIRED"
    assert client.put(f"/v1/reports/{rid}", json={"insight_md": "x"}, headers=auth("owner_seller")).status_code == 403
    too_many = client.put(f"/v1/reports/{rid}", json={"actions": [str(i) for i in range(6)]}, headers=lead)
    assert too_many.status_code == 422
    r = client.put(
        f"/v1/reports/{rid}",
        json={"insight_md": "Lãi tăng nhờ Shopee.", "actions": ["Bổ sung giá vốn SKU thiếu"]},
        headers=lead,
    )
    assert r.status_code == 200, r.text
    a = client.post(f"/v1/reports/{rid}/approve", headers=lead)
    assert a.status_code == 200 and a.json()["status"] == "approved"
    assert client.put(f"/v1/reports/{rid}", json={"insight_md": "đổi"}, headers=lead).status_code == 409

    # FR-REP-05: gửi email (luôn) cho owner với ba số và link /r/<token>.
    _run(session)
    sent = [m for _, m in drained["email"].sent if m.template == "report_ready"]
    assert sent, "phải gửi email báo cáo"
    msg = sent[0]
    assert "Doanh thu thực nhận" in msg.text and "Lãi sau phí" in msg.text
    m = re.search(r"https://app\.test/r/([\w-]+)", msg.text)
    assert m is not None
    assert client.get(f"/v1/reports/{rid}", headers=auth("owner_seller", "demo_seller")).json()["status"] == "sent"

    # FR-REP-06: mở link ghi nhận rồi chuyển tới cổng.
    o = client.get(f"/r/{m.group(1)}", follow_redirects=False)
    assert o.status_code == 302 and o.headers["location"] == f"https://app.test/app/reports/{rid}?t=demo_seller"
    opens = client.get(f"/v1/reports/{rid}/opens", headers=lead).json()
    assert any(x["opened"] for x in opens), opens
    from app.db.models import ReportOpen

    vias = {o.via for o in session.scalars(select(ReportOpen).where(ReportOpen.report_id == rid))}
    assert vias == {"portal", "email_link"}
    bad = client.get("/r/khong-ton-tai", follow_redirects=False)
    assert bad.headers["location"] == "https://app.test/report-link-invalid"
    ops = client.get("/v1/ops/reports", headers=lead).json()
    row = next(x for x in ops if x["id"] == rid)
    assert row["opened"] >= 1 and row["recipients"] >= 1


def test_fr_rep_07_snapshot_frozen_after_approve(client: Any, cube: FakeCube, session: Any) -> None:
    from app.db.models import Report

    rid = _build(client)["report_id"]
    lead = auth("data_lead")
    client.put(f"/v1/reports/{rid}", json={"insight_md": "ok"}, headers=lead)
    client.post(f"/v1/reports/{rid}/approve", headers=lead)
    cube.values["net_revenue"] = 99_000_000  # dữ liệu đổi sau khi duyệt
    again = _build(client)
    assert again == {"report_id": rid, "status": "approved", "rebuilt": False}
    session.expire_all()
    assert session.get(Report, rid).snapshot["pnl"]["net_revenue"] == 10_000_000
    new = client.post(f"/v1/reports/{rid}/supersede", headers=lead).json()
    assert new["status"] == "draft" and new["insight_md"] == "ok"
    session.expire_all()
    old = session.get(Report, rid)
    assert old.status == "superseded" and old.superseded_by == new["id"]


def test_rebuild_draft_keeps_insight(client: Any, cube: FakeCube, session: Any) -> None:
    from app.db.models import Report

    rid = _build(client)["report_id"]
    client.put(f"/v1/reports/{rid}", json={"insight_md": "giữ lại"}, headers=auth("data_lead"))
    cube.values["net_revenue"] = 11_000_000
    res = _build(client)
    assert res == {"report_id": rid, "status": "draft", "rebuilt": True}
    session.expire_all()
    rep = session.get(Report, rid)
    assert rep.insight_md == "giữ lại" and rep.snapshot["pnl"]["net_revenue"] == 11_000_000


def test_report_built_notifies_team(client: Any, cube: FakeCube, session: Any, drained: dict[str, FakeChannel]) -> None:
    from app.db.models import Notification

    _build(client)
    _run(session)
    tmpl = {n.template for n in session.scalars(select(Notification))}
    assert "report_built" in tmpl
