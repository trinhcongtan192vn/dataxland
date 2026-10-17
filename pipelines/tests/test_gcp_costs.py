"""Chi phí GCP theo khách từ billing export (spec 04 §6, FR-OPS-06)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from dx_pipelines.jobs.costs import billing_sql, run_gcp_costs


class FakeWh:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def query(self, sql: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
        self.sql.append(sql)
        if "fx_rates" in sql:
            return [(26000,)]
        if "'202609'" in sql:
            return [("demo_seller", "USD", 1.5)]
        return [("demo_seller", "USD", 2.0), ("demo_agency", "VND", 50000)]


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        self.calls.append((path, body))
        return {}


def test_fr_ops_06_gcp_costs_by_tenant_label() -> None:
    wh, api = FakeWh(), FakeApi()
    res = run_gcp_costs(wh, api, "proj-123.billing.gcp_billing_export_v1_X", today=date(2026, 10, 5))
    assert res == {"2026-09": 1, "2026-10": 2}
    assert api.calls[1] == (
        "/v1/internal/costs",
        {
            "month": "2026-10",
            "item": "gcp",
            "rows": [
                {"tenant_id": "demo_seller", "amount_vnd": "52000.00"},
                {"tenant_id": "demo_agency", "amount_vnd": "50000.00"},
            ],
        },
    )
    sql = next(s for s in wh.sql if "unnest(labels)" in s)
    assert "l.key = 'tenant_id'" in sql and "credits" in sql


def test_billing_table_validated() -> None:
    with pytest.raises(ValueError):
        billing_sql("x`; drop table y; --", date(2026, 10, 1))
