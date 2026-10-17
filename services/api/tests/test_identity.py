"""Hàng chờ ghép định danh (spec 10 §5) và chỉ số khách quay lại (spec 03 §3.2, spec 10 §7)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from tests.conftest import INTERNAL, auth
from tests.test_metrics import FakeCube


def _match(i: int, status: str = "proposed") -> dict[str, Any]:
    return {
        "entity": "product",
        "pair_key": f"shopee:{i}|tiktok_shop:{i}",
        "method": "llm",
        "score": 0.82,
        "reason_vi": "Cùng serum 30ml",
        "status": status,
        "left": {"source": "shopee", "source_id": str(i), "label": f"Serum {i}"},
        "right": {"source": "tiktok_shop", "source_id": str(i), "label": f"Tinh chất {i}"},
    }


def _seed(client: Any, n: int = 3) -> list[str]:
    r = client.post(
        "/v1/internal/identity/matches",
        headers=INTERNAL,
        json={
            "tenant_id": "demo_seller",
            "run_id": "r1",
            "suggest_run": True,
            "matches": [_match(i) for i in range(n)] + [_match(99, "approved")],
        },
    )
    assert r.json() == {"created": n + 1, "proposed": n}
    lead = auth("data_lead", "demo_seller")
    return [m["id"] for m in client.get("/v1/identity/matches?status=proposed", headers=lead).json()]


def test_fr_id_01_review_queue(client: Any, session: Any) -> None:
    ids = _seed(client)
    lead = auth("data_lead", "demo_seller")
    assert len(ids) == 3
    # Gợi ý không tự duyệt: chỉ cặp quy tắc (99) có trong danh sách đã duyệt.
    approved = client.post("/v1/internal/identity/approved", json={"tenant_id": "demo_seller"}, headers=INTERNAL)
    assert approved.json()["pairs"] == [{"left": "shopee:99", "right": "tiktok_shop:99", "method": "llm"}]
    assert client.post(f"/v1/identity/matches/{ids[0]}/approve", headers=lead).json()["status"] == "approved"
    assert client.post(f"/v1/identity/matches/{ids[1]}/reject", headers=lead).json()["status"] == "rejected"
    assert client.post(f"/v1/identity/matches/{ids[1]}/approve", headers=lead).status_code == 409
    bulk = client.post("/v1/identity/matches/bulk", json={"ids": [ids[2]], "action": "approve"}, headers=lead)
    assert [m["status"] for m in bulk.json()] == ["approved"]
    undo = client.post(f"/v1/identity/matches/{ids[0]}/undo", headers=lead)
    assert undo.json()["status"] == "undone"
    from sqlalchemy import text

    n = session.execute(text("select count(*) from events where type = 'identity.changed'")).scalar()
    assert n == 4
    acts = {r[0] for r in session.execute(text("select action from audit_log where action like 'identity.%'"))}
    assert {"identity.approve", "identity.reject", "identity.undo", "identity.suggest_run"} <= acts
    keys = client.post("/v1/internal/identity/matches/keys", json={"tenant_id": "demo_seller"}, headers=INTERNAL)
    assert len(keys.json()["pair_keys"]) == 4 and keys.json()["last_suggest_at"]


def test_existing_decision_kept_on_rerun(client: Any) -> None:
    ids = _seed(client, 1)
    lead = auth("data_lead", "demo_seller")
    client.post(f"/v1/identity/matches/{ids[0]}/reject", headers=lead)
    again = client.post(
        "/v1/internal/identity/matches", headers=INTERNAL, json={"tenant_id": "demo_seller", "matches": [_match(0)]}
    )
    assert again.json() == {"created": 0, "proposed": 0}


def test_identity_permissions(client: Any) -> None:
    assert client.get("/v1/identity/matches", headers=auth("owner_seller", "demo_seller")).status_code == 403
    ids = _seed(client, 1)
    eng = auth("engineer", "demo_seller")
    assert client.get("/v1/identity/matches", headers=eng).status_code == 200
    assert client.post(f"/v1/identity/matches/{ids[0]}/approve", headers=eng).status_code == 403


class CustomerCube(FakeCube):
    """Trả số đơn theo người mua khi truy vấn có chiều `customer`."""

    def load(self, tenant_id: str, dataset_prefix: str, query: dict[str, Any]) -> list[dict[str, Any]]:
        dims = query.get("dimensions", [])
        if any(d.endswith(".customer") for d in dims):
            self.calls.append((tenant_id, dataset_prefix, query))
            cube = dims[0].split(".")[0]
            counts = {"c1": 3, "c2": 1, "c3": 2, "c4": 1}
            return [{f"{cube}.customer": c, f"{cube}.order_count": str(n)} for c, n in counts.items()]
        if any(m.endswith(".active_customers") for m in query.get("measures", [])):
            self.calls.append((tenant_id, dataset_prefix, query))
            return [{query["measures"][0]: "4"}]
        return super().load(tenant_id, dataset_prefix, query)


@pytest.fixture()
def ccube(monkeypatch: pytest.MonkeyPatch) -> Iterator[CustomerCube]:
    from app.metrics.cube_client import set_cube

    monkeypatch.setenv("DX_TODAY", "2026-10-16")
    fake = CustomerCube()
    set_cube(fake)
    yield fake
    set_cube(None)


def test_repeat_customer_rate_two_step(client: Any, ccube: CustomerCube) -> None:
    r = client.post(
        "/v1/metrics/query",
        json={"metrics": ["repeat_customer_rate"], "time": {"preset": "last_30_days"}},
        headers=auth("owner_seller", "demo_seller"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["rows"][0]["repeat_customer_rate"] == pytest.approx(0.5)  # c1, c3 / 4 người mua
    assert r.json()["metrics"]["repeat_customer_rate"]["unit"] == "percent"


def test_customer_dimension_is_internal(client: Any, ccube: CustomerCube) -> None:
    r = client.post(
        "/v1/metrics/query",
        json={"metrics": ["order_count"], "dimensions": ["customer"]},
        headers=auth("owner_seller", "demo_seller"),
    )
    assert r.status_code == 400 and r.json()["code"] == "DIMENSION_NOT_ALLOWED"


def test_repeat_rate_requires_identity(client: Any, ccube: CustomerCube) -> None:
    names = {m["metric"] for m in client.get("/v1/metrics", headers=auth("owner_seller", "demo_seller")).json()}
    assert "repeat_customer_rate" in names
