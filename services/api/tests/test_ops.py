"""FR-OPS-02, FR-OPS-04, spec 05 §6.9, spec 04 §2, §6."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from tests.conftest import INTERNAL, REPO, auth


def _load_ops(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, REPO / "ops" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_fr_ops_04_overview_reflects_runs(client: Any) -> None:
    body = {
        "run_id": "r-1",
        "tenant_id": "demo_seller",
        "job": "tenant_pipeline",
        "status": "running",
        "step": "sync_sources",
        "step_status": "success",
        "sources": [
            {"source": "shopee", "account_id": "100001", "status": "success", "rows_loaded": 12},
            {"source": "lazada", "account_id": "300001", "status": "failed", "error_code": "auth_revoked"},
        ],
    }
    assert client.post("/v1/internal/runs", json=body, headers=INTERNAL).status_code == 204
    blocked = {
        "run_id": "r-1",
        "tenant_id": "demo_seller",
        "job": "tenant_pipeline",
        "status": "blocked",
        "failed_step": "evaluate_tests",
        "blocking_failures": [{"test": "reconcile_daily_totals_shopee", "severity": "error", "rows": []}],
    }
    assert client.post("/v1/internal/runs", json=blocked, headers=INTERNAL).status_code == 204
    rows = client.get("/v1/ops/overview", headers=auth("data_lead")).json()
    seller = next(r for r in rows if r["tenant_id"] == "demo_seller")
    colors = {c["source"]: c["color"] for c in seller["sources"]}
    assert colors["shopee"] == "green" and colors["lazada"] == "red" and colors["tiktok_shop"] == "grey"
    assert seller["blocking_tests"] == 1 and seller["last_run"]["status"] == "blocked"
    assert seller["weekly_report"]["status"] == "not_built"
    assert seller["source_count"] == 4
    # Chỉ nhân viên vào được /ops.
    assert client.get("/v1/ops/overview", headers=auth("owner_seller")).status_code == 403
    assert client.get("/v1/ops/overview", headers=auth("engineer")).status_code == 200
    runs = client.get("/v1/ops/tenants/demo_seller/runs", headers=auth("engineer")).json()
    assert runs[0]["failed_step"] == "evaluate_tests"
    latest = client.post(
        "/v1/internal/runs/latest", json={"tenant_id": "demo_seller", "status": "blocked"}, headers=INTERNAL
    ).json()
    assert latest["run_id"] == "r-1"


def test_rerun_publishes_event_and_requires_ops_write(client: Any, session: Any) -> None:
    from dx_common.events.tables import events

    assert client.post("/v1/ops/tenants/demo_seller/runs", json={}, headers=auth("engineer")).status_code == 403
    r = client.post("/v1/ops/tenants/demo_seller/runs", json={"full_refresh": True}, headers=auth("data_lead"))
    assert r.status_code == 202
    ev = session.execute(events.select().where(events.c.type == "pipeline.requested")).one()
    assert ev.payload["full_refresh"] is True


def test_manual_fx_rate(client: Any) -> None:
    r = client.post(
        "/v1/admin/fx-rates",
        json={"date": "2026-10-11", "currency": "USD", "rate_vnd": 26100.5},
        headers=auth("data_lead"),
    )
    assert r.status_code == 201
    assert client.get("/v1/admin/fx-rates", headers=auth("data_lead")).json()[0]["currency"] == "USD"
    assert (
        client.post(
            "/v1/admin/fx-rates",
            json={"date": "2026-10-11", "currency": "USD", "rate_vnd": 1},
            headers=auth("engineer"),
        ).status_code
        == 403
    )


def test_fr_ops_02_bootstrap_idempotent(session: Any, tmp_path: Path) -> None:
    from app.db.models import Tenant
    from dx_common.config import Settings
    from dx_common.events.tables import events
    from dx_common.secrets import LocalFileSecretStore

    mod = _load_ops("bootstrap_tenant")
    session.get(Tenant, "demo_agency").bootstrap_required = True
    session.commit()
    s = Settings(dx_env="local", duckdb_path=str(tmp_path / "dx.duckdb"), secrets_dir=str(tmp_path / "secrets"))
    store = LocalFileSecretStore(tmp_path / "secrets")
    r1 = mod.bootstrap(session, "demo_agency", settings=s, store=store)
    session.commit()
    salt = store.get("dx-demo_agency-pii-salt")
    r2 = mod.bootstrap(session, "demo_agency", settings=s, store=store)
    session.commit()
    assert sorted(r1.created_datasets) == [
        "t_demo_agency_core",
        "t_demo_agency_marts",
        "t_demo_agency_raw",
        "t_demo_agency_stg",
    ]
    assert r2.created_datasets == [] and len(r2.existing_datasets) == 4
    assert r1.salt_created and not r2.salt_created and store.get("dx-demo_agency-pii-salt") == salt
    assert r1.published_created and not r2.published_created
    n = session.scalar(select(func.count()).select_from(events).where(events.c.type == "tenant.created"))
    assert n == 1
    assert "dx-demo_agency-shopee-100002" in r1.missing_secrets
    assert any("Windsor" in c for c in r1.checklist)
