"""FR-OPS-03, FR-DQ-04 (phần điều phối), spec 04 §3.2."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from connectors.base import SourceError, SyncOutcome
from dx_common.tenants import load_tenant_file
from dx_pipelines.dbt import DbtResult
from dx_pipelines.runner import STEPS, Services, TenantPipeline
from dx_pipelines.warehouse import DuckDBWarehouse

REPO = Path(__file__).resolve().parents[2]


class FakeApi:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.runs: list[dict[str, Any]] = []
        self.anomalies = 0

    def record_run(self, body: dict[str, Any]) -> None:
        self.runs.append(body)

    def publish(self, type: str, tenant_id: str | None, payload: dict[str, Any], producer: str) -> str:
        self.events.append((type, payload))
        return "e"

    def run_anomalies(self, tenant_id: str, run_id: str) -> dict[str, Any]:
        self.anomalies += 1
        return {}

    def post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"pair_keys": [], "pairs": [], "last_suggest_at": None}


class FakeDbt:
    def __init__(self, fail_tests: bool = False, runtime_error: bool = False, swap_ok: bool = True) -> None:
        self.fail_tests, self.runtime_error, self.swap_ok = fail_tests, runtime_error, swap_ok
        self.swapped = False

    def freshness(self, vars: dict[str, Any], target_path: Path, env: dict[str, str]) -> DbtResult:
        return DbtResult("freshness", 0, target_path, sources={"results": []})

    def build(self, vars: dict[str, Any], target_path: Path, env: dict[str, str], **kw: Any) -> DbtResult:
        results: list[dict[str, Any]] = [{"unique_id": "model.dx.fct_order", "status": "success"}]
        if self.runtime_error:
            results.append({"unique_id": "model.dx.fct_cost", "status": "error", "message": "boom"})
        if self.fail_tests:
            results.append({"unique_id": "test.dx.reconcile_daily_totals_shopee.abc", "status": "fail", "failures": 1})
        results.append({"unique_id": "test.dx.volume_anomalies_fct_order.x", "status": "warn"})
        return DbtResult(
            "build", 1 if (self.fail_tests or self.runtime_error) else 0, target_path, run_results={"results": results}
        )

    def run_operation(
        self, macro: str, args: dict[str, Any], vars: dict[str, Any], target_path: Path, env: dict[str, str]
    ) -> DbtResult:
        self.swapped = True
        return DbtResult(macro, 0 if self.swap_ok else 2, target_path)


class FakeCube:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def refresh(self, tenant_id: str, dataset_prefix: str) -> dict[str, Any]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("cube down")
        return {}


@pytest.fixture()
def wh(tmp_path: Path) -> DuckDBWarehouse:
    w = DuckDBWarehouse(tmp_path / "dx.duckdb")
    now = datetime.now(UTC).replace(tzinfo=None)
    for t in ("meta_ads__ad_insights_daily",):
        w.write_rows("t_demo_seller_raw", t, {"_dx_loaded_at": "timestamp"}, [{"_dx_loaded_at": now}])
    w.write_rows("t_demo_seller_marts", "mrt_common__data_status", {"data_as_of": "timestamp"}, [{"data_as_of": now}])
    return w


def _pipeline(wh: DuckDBWarehouse, tmp_path: Path, **kw: Any) -> tuple[TenantPipeline, FakeApi, FakeDbt, FakeCube]:
    tenant = load_tenant_file(REPO / "tenants" / "demo_seller.yml")
    api, dbt, cube = FakeApi(), kw.pop("dbt", FakeDbt()), kw.pop("cube", FakeCube())
    conn = kw.pop("connector", lambda t, s, c: SyncOutcome(rows_loaded=3))

    def connector_for(src: Any) -> Any:
        return None if src.connector == "windsor" else conn

    svc = Services(
        api=api, warehouse=wh, dbt=dbt, cube=cube, connector_for=connector_for, upload_metadata=lambda *a: [], repo=REPO
    )
    p = TenantPipeline(tenant, "run-1", svc)
    p.target_path = tmp_path / "target"
    return p, api, dbt, cube


def test_happy_path_runs_all_steps(wh: DuckDBWarehouse, tmp_path: Path) -> None:
    p, api, dbt, cube = _pipeline(wh, tmp_path)
    out = p.run()
    assert out.status == "success"
    assert list(out.steps) == list(STEPS) and set(out.steps.values()) == {"success"}
    assert [e for e, _ in api.events] == ["transform.finished"]
    assert dbt.swapped and cube.calls == 1 and api.anomalies == 1
    assert out.warnings and "volume_anomalies" in out.warnings[0]  # test cảnh báo không chặn (FR-DQ-03)
    assert api.runs[-1]["status"] == "success"


@pytest.mark.parametrize(
    ("kw", "failed_step", "reason"),
    [
        ({"connector": None}, "sync_sources", "auth_revoked"),
        ({"dbt": FakeDbt(runtime_error=True)}, "dbt_build", "dbt_error"),
        ({"dbt": FakeDbt(swap_ok=False)}, "swap_marts", "swap_failed"),
        ({"cube": FakeCube(fail=True)}, "refresh_cube", "cube_refresh_failed"),
    ],
)
def test_fr_ops_03_step_failure_stops_pipeline(
    wh: DuckDBWarehouse, tmp_path: Path, kw: dict[str, Any], failed_step: str, reason: str
) -> None:
    if "connector" in kw:

        def bad(t: Any, s: Any, c: Any) -> SyncOutcome:
            raise SourceError("auth_revoked", "refresh token bị thu hồi")

        kw["connector"] = bad
    p, api, dbt, cube = _pipeline(wh, tmp_path, **kw)
    out = p.run()
    assert out.status == "failed" and out.failed_step == failed_step
    idx = STEPS.index(failed_step)
    assert all(s not in out.steps for s in STEPS[idx + 1 :]), out.steps
    assert [(e, pl["reason"]) for e, pl in api.events] == [("sync.failed", reason)]
    assert "transform.finished" not in [e for e, _ in api.events]
    assert api.runs[-1]["status"] == "failed" and api.runs[-1]["failed_step"] == failed_step


def test_windsor_stale_stops_pipeline(tmp_path: Path) -> None:
    w = DuckDBWarehouse(tmp_path / "dx.duckdb")
    old = datetime(2020, 1, 1)
    w.write_rows(
        "t_demo_seller_raw", "meta_ads__ad_insights_daily", {"_dx_loaded_at": "timestamp"}, [{"_dx_loaded_at": old}]
    )
    p, api, _, _ = _pipeline(w, tmp_path)
    out = p.run()
    assert out.failed_step == "check_windsor_freshness"
    assert api.events[0][1]["reason"] == "windsor_stale"


def test_fr_dq_04_blocked_run_does_not_swap_or_refresh(wh: DuckDBWarehouse, tmp_path: Path) -> None:
    dbt = FakeDbt(fail_tests=True)
    p, api, dbt, cube = _pipeline(wh, tmp_path, dbt=dbt)
    out = p.run()
    assert out.status == "blocked" and out.failed_step == "evaluate_tests"
    assert not dbt.swapped and cube.calls == 0 and api.anomalies == 0
    assert [e for e, _ in api.events] == ["test.failed"]
    assert api.events[0][1]["failures"][0]["test"] == "reconcile_daily_totals_shopee"
    assert api.runs[-1]["status"] == "blocked"


def test_override_invalid(wh: DuckDBWarehouse, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p, api, _, _ = _pipeline(wh, tmp_path)
    p.tenant.overrides.status_map = "tenants/overrides/nope.csv"
    out = p.run()
    assert out.failed_step == "load_overrides" and api.events[0][1]["reason"] == "override_invalid"
