"""Chi phí và giờ người theo khách (spec 04 §6, FR-OPS-06)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from tests.conftest import INTERNAL, auth


def test_split_sums_exactly() -> None:
    from app.routers.costs import split

    out = split(Decimal(1000), {"a": Decimal(1), "b": Decimal(1), "c": Decimal(1)})
    assert sum(out.values()) == 1000 and sorted(out.values()) == [333, 333, 334]
    assert split(Decimal(10), {"a": Decimal(0)}) == {}


def test_fr_ops_06_gcp_costs_internal(client: Any) -> None:
    body = {
        "month": "2026-10",
        "item": "gcp",
        "rows": [
            {"tenant_id": "demo_seller", "amount_vnd": "120000.50"},
            {"tenant_id": "unknown_tenant", "amount_vnd": "999"},
        ],
    }
    assert client.post("/v1/internal/costs", json=body, headers=INTERNAL).status_code == 204
    # Chạy lại thay toàn bộ mục của tháng, không cộng dồn.
    assert client.post("/v1/internal/costs", json=body, headers=INTERNAL).status_code == 204
    rows = {r["tenant_id"]: r for r in client.get("/v1/ops/costs?month=2026-10", headers=auth("data_lead")).json()}
    assert rows["demo_seller"]["items"] == {"gcp": 120000} and "unknown_tenant" not in rows
    assert client.post("/v1/internal/costs", json=body, headers=auth("data_lead")).status_code in (401, 403)


def test_fr_ops_06_allocate_and_hours(client: Any, session: Any) -> None:
    from app.db.models import TenantCost

    h = auth("data_lead")
    # Windsor: theo số nguồn Windsor đang bật (demo_agency 5, demo_seller 1).
    r = client.post(
        "/v1/ops/costs/allocate", json={"month": "2026-10", "item": "windsor", "amount_vnd": 1500000}, headers=h
    )
    assert r.status_code == 200, r.text
    assert r.json()["allocated"] == {"demo_agency": 1250000, "demo_seller": 250000}
    # Claude: theo chi phí AI ước tính đã ghi; hóa đơn thật thay số ước tính.
    oct_ = date(2026, 10, 1)
    session.add(TenantCost(month=oct_, tenant_id="demo_seller", item="ai", amount_vnd=300))
    session.add(TenantCost(month=oct_, tenant_id="demo_agency", item="ai", amount_vnd=100))
    session.commit()
    r = client.post(
        "/v1/ops/costs/allocate", json={"month": "2026-10", "item": "claude", "amount_vnd": 800000}, headers=h
    )
    assert r.json()["allocated"] == {"demo_seller": 600000, "demo_agency": 200000}
    session.expire_all()
    ai = {c.tenant_id: int(c.amount_vnd) for c in session.scalars(select(TenantCost).where(TenantCost.item == "ai"))}
    assert ai == {"demo_seller": 600000, "demo_agency": 200000}

    assert (
        client.put(
            "/v1/ops/tenants/demo_seller/hours",
            json={"month": "2026-10", "hours": 6.5, "note": "onboarding"},
            headers=h,
        ).status_code
        == 204
    )
    assert (
        client.put("/v1/ops/tenants/demo_seller/hours", json={"month": "2026-10", "hours": 8}, headers=h).status_code
        == 204
    )
    rows = {r["tenant_id"]: r for r in client.get("/v1/ops/costs?month=2026-10", headers=h).json()}
    assert rows["demo_seller"]["hours"] == 8 and rows["demo_seller"]["total_vnd"] == 850000
    assert rows["demo_agency"]["items"] == {"windsor": 1250000, "ai": 200000}
    # Engineer chỉ xem; khách không vào được.
    assert client.get("/v1/ops/costs", headers=auth("engineer")).status_code == 200
    assert (
        client.post(
            "/v1/ops/costs/allocate",
            json={"month": "2026-10", "item": "windsor", "amount_vnd": 1},
            headers=auth("engineer"),
        ).status_code
        == 403
    )
    assert client.get("/v1/ops/costs", headers=auth("owner_seller")).status_code == 403
    overview = {r["tenant_id"]: r for r in client.get("/v1/ops/overview", headers=h).json()}
    assert overview["demo_agency"]["costs_month_vnd"] in (None, 1450000)
