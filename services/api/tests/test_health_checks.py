"""Kiểm tra sức khỏe phía API (spec 07 §9, §10): FR-HC-01, FR-HC-03..05."""

from __future__ import annotations

import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.conftest import INTERNAL, REPO, FakeChannel, auth
from tests.test_metrics import FakeCube

SAMPLES = REPO / "transform" / "samples" / "files"


@pytest.fixture()
def hc_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    from dx_common.config import reset_settings_cache

    monkeypatch.setenv("HC_BUCKET", str(tmp_path / "hc"))
    monkeypatch.setenv("DX_TODAY", "2026-10-16")
    reset_settings_cache()
    yield tmp_path / "hc"
    reset_settings_cache()


@pytest.fixture()
def cube() -> Iterator[FakeCube]:
    from app.metrics.cube_client import set_cube

    fake = FakeCube()
    set_cube(fake)
    yield fake
    set_cube(None)


def _submit(client: Any, files: list[tuple[str, str]], **extra: Any) -> Any:
    version = client.get("/v1/health-checks/consent").json()["version"]
    data: dict[str, Any] = {
        "email": "Chu.Shop@Example.com",
        "shop_name": "Shop Thử",
        "consent_version": version,
        "kinds": [k for _, k in files],
        "started_at": str(int((time.time() - 30) * 1000)),
    }
    data.update(extra)
    up = [("files", (n, (SAMPLES / n).read_bytes(), "application/octet-stream")) for n, _ in files]
    return client.post("/v1/health-checks", data=data, files=up)


def _verify_token(channels: dict[str, FakeChannel]) -> str:
    msg = next(m for _, m in channels["email"].sent if m.template == "healthcheck_verify")
    found = re.search(r"verify\?token=([\w-]+)", msg.text)
    assert found
    return found.group(1)


def test_consent_text_and_kinds(client: Any) -> None:
    r = client.get("/v1/health-checks/consent").json()
    assert "Singapore" in r["text_md"] and "14 ngày" in r["text_md"]
    assert r["kinds"]["shopee_orders"] and r["max_files"] == 10 and r["retention_days"] == 14


def test_fr_hc_01_submit_validation(client: Any, hc_env: Path, channels: dict[str, FakeChannel]) -> None:
    bad = _submit(client, [("shopee_orders.xlsx", "khong_co")])
    assert bad.status_code == 422 and bad.json()["code"] == "KIND_INVALID"
    honeypot = _submit(client, [("shopee_orders.xlsx", "shopee_orders")], website="spam")
    assert honeypot.status_code == 400
    fast = _submit(client, [("shopee_orders.xlsx", "shopee_orders")], started_at=str(int(time.time() * 1000)))
    assert fast.json()["code"] == "TOO_FAST"
    old = _submit(client, [("shopee_orders.xlsx", "shopee_orders")], consent_version="2000-01-01")
    assert old.json()["code"] == "CONSENT_OUTDATED"


def test_full_flow(client: Any, hc_env: Path, cube: FakeCube, channels: dict[str, FakeChannel], session: Any) -> None:
    from app.db.models import HealthCheck, HealthCheckFile

    r = _submit(
        client,
        [
            ("shopee_orders.xlsx", "shopee_orders"),
            ("shopee_income.xlsx", "shopee_income"),
            ("meta_ads.csv", "meta_ads"),
        ],
    )
    assert r.status_code == 202, r.text
    cid = r.json()["check_id"]
    hc = session.get(HealthCheck, cid)
    assert hc.status == "uploaded" and hc.email == "chu.shop@example.com"
    assert len(list((hc_env / cid).iterdir())) == 3
    # Dagster chưa được chạy trước khi xác nhận email.
    assert client.post(f"/v1/internal/health-checks/{cid}/start", headers=INTERNAL).status_code == 409
    v = client.get(f"/v1/health-checks/verify?token={_verify_token(channels)}").json()
    assert v["status"] == "verified"
    from sqlalchemy import text

    assert session.execute(text("select count(*) from events where type = 'healthcheck.submitted'")).scalar() == 1

    start = client.post(f"/v1/internal/health-checks/{cid}/start", headers=INTERNAL).json()
    assert len(start["files"]) == 3 and len(start["salt"]) == 64
    files = [
        {
            "id": f["id"],
            "status": "loaded",
            "detected_kind": f["declared_kind"],
            "rows_loaded": 10,
            "date_from": "2026-09-01",
            "date_to": "2026-10-15",
        }
        for f in start["files"]
    ]
    client.post(f"/v1/internal/health-checks/{cid}/files", json={"files": files}, headers=INTERNAL)
    b = client.post(f"/v1/internal/health-checks/{cid}/build", json={"mapping_issues": []}, headers=INTERNAL)
    assert b.status_code == 200, b.text
    assert all(t == f"hc_{cid}" and p == f"hc_{cid}" for t, p, _ in cube.calls)

    # FR-HC-03: kết quả có đủ phần; chưa duyệt thì link kết quả 404.
    lead = auth("data_lead")
    d = client.get(f"/v1/ops/health-checks/{cid}", headers=lead).json()
    res = d["result"]
    assert {"overview", "fees", "loss_skus", "returns", "source_gaps", "file_quality", "metrics"} <= set(res)
    assert res["overview"]["profit_metric"] == "contribution_margin" and res["loss_skus"]["before_cogs"]
    assert "ads" in res["source_gaps"]
    assert client.get(f"/v1/health-checks/{cid}/result?k=x").status_code == 404
    assert client.get("/v1/ops/health-checks", headers=auth("owner_seller")).status_code == 403

    client.put(f"/v1/ops/health-checks/{cid}", json={"reviewer_notes_md": "Phí sàn ăn 18% doanh thu."}, headers=lead)
    a = client.post(f"/v1/ops/health-checks/{cid}/approve", headers=lead).json()
    assert a["status"] == "approved" and a["email_sent"]
    k = a["result_url"].split("k=")[1]
    ready = next(m for _, m in channels["email"].sent if m.template == "healthcheck_ready")
    assert a["result_url"] in ready.text
    pub = client.get(f"/v1/health-checks/{cid}/result?k={k}").json()
    assert pub["reviewer_notes_md"].startswith("Phí sàn") and "file_quality" not in pub["result"]
    c = client.post(f"/v1/health-checks/{cid}/consent-convert?k={k}").json()
    assert c["consent_convert_at"]

    # FR-HC-05: bản nháp cấu hình qua được kiểm tra như CI.
    conv = client.post(
        f"/v1/ops/health-checks/{cid}/convert", json={"tenant_id": "shop_thu", "pack": "seller"}, headers=lead
    ).json()
    doc = yaml.safe_load(conv["yaml"])
    assert doc["tenant_id"] == "shop_thu" and {s["type"] for s in doc["sources"]} == {"shopee", "meta_ads"}
    assert conv["copy_raw_allowed"] is True
    session.expire_all()
    assert session.get(HealthCheck, cid).status == "converted"
    assert session.query(HealthCheckFile).filter_by(check_id=cid).count() == 3


def test_fr_hc_04_expired_listing_and_mark(
    client: Any, hc_env: Path, channels: dict[str, FakeChannel], session: Any
) -> None:
    from datetime import timedelta

    from app.db.models import HealthCheck

    cid = _submit(client, [("meta_ads.csv", "meta_ads")]).json()["check_id"]
    keep = _submit(client, [("meta_ads.csv", "meta_ads")]).json()["check_id"]
    for c in (cid, keep):
        h = session.get(HealthCheck, c)
        h.expires_at = h.expires_at - timedelta(days=15)
    session.get(HealthCheck, keep).status = "converted"
    session.commit()
    items = client.post("/v1/internal/health-checks/expired", headers=INTERNAL).json()["items"]
    assert {i["check_id"] for i in items} == {cid}
    r = client.post(f"/v1/internal/health-checks/{cid}/expired", json={"tables": 12, "files": 1}, headers=INTERNAL)
    assert r.json()["status"] == "expired"
    assert client.post(f"/v1/internal/health-checks/{keep}/expired", json={}, headers=INTERNAL).status_code == 409
    session.expire_all()
    h = session.get(HealthCheck, cid)
    assert h.deleted_at is not None and h.result is None and h.funnel_counts["files"] == 1
    assert client.post("/v1/internal/health-checks/expired", headers=INTERNAL).json()["items"] == []


def test_fr_hc_02_no_metric_sql_outside_semantic() -> None:
    """Không có SQL tính chỉ số trong services/api và connectors/files: mọi số đi qua lớp chỉ số."""
    roots = [REPO / "services" / "api" / "app", REPO / "pipelines" / "connectors" / "files"]
    # Một chuỗi SQL trên cùng một dòng có `select ... sum(`/`avg(`; không bắt `select(func.sum(...))` của SQLAlchemy.
    pattern = re.compile(r"""["'][^"'\n]*\bselect\b[^"'\n]*\b(sum|avg)\s*\(""", re.IGNORECASE)
    offenders = [str(p) for root in roots for p in root.rglob("*.py") if pattern.search(p.read_text(encoding="utf-8"))]
    assert offenders == []
