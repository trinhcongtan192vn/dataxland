"""Lớp chỉ số qua API với Cube giả (spec 03 §11): FR-MET-03/05/06, FR-AUTH-03, FR-AUTH-05, tách biệt khách."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pytest

from tests.conftest import auth


class FakeCube:
    """Trả giá trị cố định theo tên measure; ghi lại (tenant_id, dataset_prefix, query) của mọi lần gọi."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.values: dict[str, float] = {
            "net_revenue": 10_000_000,
            "order_count": 40,
            "net_revenue_sales": 9_000_000,
            "ad_spend": 3_000_000,
            "cancelled_orders": 5,
            "orders_placed": 50,
            "gmv": 12_000_000,
        }

    def load(self, tenant_id: str, dataset_prefix: str, query: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls.append((tenant_id, dataset_prefix, query))
        if "measures" not in query:  # cube trạng thái dữ liệu
            cube = query["dimensions"][0].split(".")[0]
            return [
                {
                    f"{cube}.data_as_of": "2026-10-16T00:00:00.000",
                    f"{cube}.provisional_revenue_share": "0",
                    f"{cube}.missing_cogs_sku_count": "2",
                    f"{cube}.missing_cogs_revenue_vnd": "1500000",
                }
            ]
        row: dict[str, Any] = {}
        for m in query["measures"]:
            row[m] = str(self.values.get(m.split(".", 1)[1], 1000))
        for d in query.get("dimensions", []):
            row[d] = "shopee"
        return [row]


@pytest.fixture()
def cube() -> Iterator[FakeCube]:
    from app.metrics.cube_client import set_cube

    fake = FakeCube()
    set_cube(fake)
    yield fake
    set_cube(None)


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DX_TODAY", "2026-10-16")
    monkeypatch.setenv("DX_NOW", "2026-10-16T03:00:00Z")


def _q(client: Any, key: str, tenant: str, body: dict[str, Any]) -> Any:
    return client.post("/v1/metrics/query", json=body, headers=auth(key, tenant))


def test_fr_met_06_response_has_version_and_as_of(client: Any, cube: FakeCube) -> None:
    r = _q(client, "owner_seller", "demo_seller", {"metrics": ["net_revenue"], "time": {"preset": "last_week"}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["time"] == {"from": "2026-10-05", "to": "2026-10-11", "grain": "none"}
    assert body["metrics"]["net_revenue"]["version"]
    assert body["rows"][0]["net_revenue"] == 10_000_000
    assert body["data_as_of"] == "2026-10-16T00:00:00Z"


def test_fr_met_05_ratio_is_ratio_of_sums(client: Any, cube: FakeCube) -> None:
    r = _q(
        client,
        "owner_seller",
        "demo_seller",
        {"metrics": ["aov", "cancel_rate", "roas_blended"], "time": {"preset": "last_30_days"}},
    )
    assert r.status_code == 200, r.text
    row = r.json()["rows"][0]
    # Tỷ lệ trong cùng một cube: Cube tính tỷ lệ của tổng (measure sinh từ YAML).
    calls = [c[2]["measures"] for c in cube.calls if "measures" in c[2]]
    assert ["mrt_seller__orders.aov", "mrt_seller__orders.cancel_rate"] in calls
    # Tỷ lệ qua hai cube (doanh thu ÷ chi quảng cáo): API tính từ hai tổng, không lấy trung bình theo ngày.
    assert ["mrt_common__sales_daily.net_revenue_sales"] in calls and ["mrt_common__ad_daily.ad_spend"] in calls
    assert row["roas_blended"] == pytest.approx(3.0)


def test_fr_inp_03_missing_cogs_warning(client: Any, cube: FakeCube) -> None:
    r = _q(
        client, "owner_seller", "demo_seller", {"metrics": ["net_profit_after_fees"], "time": {"preset": "last_week"}}
    )
    warns = {w["code"]: w for w in r.json()["warnings"]}
    assert "MISSING_COGS" in warns
    assert "1.500.000 ₫" in warns["MISSING_COGS"]["detail_vi"]
    r2 = _q(client, "owner_seller", "demo_seller", {"metrics": ["net_revenue"], "time": {"preset": "last_week"}})
    assert "MISSING_COGS" not in {w["code"] for w in r2.json()["warnings"]}


def test_compare_previous_period(client: Any, cube: FakeCube) -> None:
    r = _q(
        client,
        "owner_seller",
        "demo_seller",
        {"metrics": ["net_revenue"], "time": {"preset": "last_week"}, "compare": "previous_period"},
    )
    assert r.json()["rows"][0]["compare"]["net_revenue"] == 10_000_000
    ranges = [c[2]["timeDimensions"][0]["dateRange"] for c in cube.calls if "measures" in c[2]]
    assert ["2026-09-28", "2026-10-04"] in ranges


def test_fr_auth_03_member_allowlist(client: Any, cube: FakeCube) -> None:
    ok = _q(client, "member_seller", "demo_seller", {"metrics": ["net_revenue"], "time": {"preset": "last_week"}})
    assert ok.status_code == 200
    denied = _q(
        client, "member_seller", "demo_seller", {"metrics": ["net_profit_after_fees"], "time": {"preset": "last_week"}}
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "METRIC_FORBIDDEN"
    names = {m["metric"] for m in client.get("/v1/metrics", headers=auth("member_seller", "demo_seller")).json()}
    assert names == {"net_revenue", "order_count"}
    # Thành phần ẩn của chỉ số tổng hợp cũng không truy vấn trực tiếp được.
    hidden = _q(client, "owner_seller", "demo_seller", {"metrics": ["orders_placed"], "time": {"preset": "last_week"}})
    assert hidden.status_code == 400


def test_pack_metric_forbidden(client: Any, cube: FakeCube) -> None:
    r = _q(
        client, "owner_agency", "demo_agency", {"metrics": ["net_profit_after_fees"], "time": {"preset": "last_week"}}
    )
    assert r.status_code == 403


def test_partner_sees_only_agency_metrics(client: Any, cube: FakeCube) -> None:
    names = {m["metric"] for m in client.get("/v1/metrics", headers=auth("partner", "demo_agency")).json()}
    assert "roas_blended" in names
    assert "net_profit_after_fees" not in names


def test_isolation_tenant_from_auth_not_params(client: Any, cube: FakeCube) -> None:
    """Người gọi của demo_seller không đọc được demo_agency, dù có ghi tenant_id trong body."""
    r = client.post(
        "/v1/metrics/query",
        json={"metrics": ["ad_spend"], "tenant_id": "demo_agency"},
        headers=auth("owner_seller", "demo_seller"),
    )
    assert r.status_code == 200
    assert r.json()["tenant_id"] == "demo_seller"
    assert {(t, p) for t, p, _ in cube.calls} == {("demo_seller", "demo_seller")} or all(
        t == "demo_seller" and "agency" not in p for t, p, _ in cube.calls
    )
    cube.calls.clear()
    other = _q(client, "owner_seller", "demo_agency", {"metrics": ["ad_spend"]})
    assert other.status_code == 403
    assert cube.calls == []


def test_fr_auth_05_no_pii_dimension_or_output(client: Any, cube: FakeCube) -> None:
    for dim in ("buyer_phone", "buyer_email", "buyer_name", "shipping_address"):
        r = _q(client, "owner_seller", "demo_seller", {"metrics": ["net_revenue"], "dimensions": [dim]})
        assert r.status_code == 400
    r = _q(client, "owner_seller", "demo_seller", {"metrics": ["net_revenue"], "dimensions": ["platform"]})
    text = r.text
    assert not re.search(r"(?<![0-9a-f])0\d{9}(?![0-9a-f])", text)
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)


def test_query_limits(client: Any, cube: FakeCube) -> None:
    many = ["net_revenue"] * 1 + [
        "gmv",
        "aov",
        "order_count",
        "cancel_rate",
        "return_rate",
        "cogs",
        "ad_spend",
        "roas_blended",
        "platform_fees",
        "shipping_cost",
    ]
    r = _q(client, "owner_seller", "demo_seller", {"metrics": many})
    assert r.status_code == 400 and r.json()["code"] == "TOO_MANY_METRICS"


def test_key_numbers_seller(client: Any, cube: FakeCube) -> None:
    r = client.get("/v1/metrics/key-numbers?period=last_week", headers=auth("owner_seller", "demo_seller"))
    assert r.status_code == 200, r.text
    nums = r.json()["numbers"]
    assert [n["key"] for n in nums] == ["net_revenue", "net_profit_after_fees", "net_profit_change_pct"]
    assert nums[2]["label_vi"] == "Lãi so với tuần trước"


def test_key_numbers_bad_period(client: Any, cube: FakeCube) -> None:
    r = client.get("/v1/metrics/key-numbers?period=yesterday", headers=auth("owner_seller", "demo_seller"))
    assert r.status_code == 400


def test_query_log_written(client: Any, cube: FakeCube, session: Any) -> None:
    from sqlalchemy import text

    _q(client, "owner_seller", "demo_seller", {"metrics": ["net_revenue"]})
    n = session.execute(text("select count(*) from metric_queries where tenant_id = 'demo_seller'")).scalar()
    assert n and n >= 1
