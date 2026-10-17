"""Agent nội bộ trong worker (spec 09 §8): weekly-insight, incident-triage."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from tests.conftest import INTERNAL, auth
from tests.test_ask import FakeModel, reply, tool_use
from tests.test_reports import _build, cube  # noqa: F401 - fixture

DRAFT = "Doanh thu thực nhận tuần này giữ ổn định; chú ý 2 SKU chưa có giá vốn."


def _insight_model() -> FakeModel:
    return FakeModel(
        [
            reply(
                tool_use(
                    1,
                    "insight_draft",
                    {"insight_md": DRAFT, "actions": ["Nhập giá vốn cho 2 SKU còn thiếu", " ", "Xem lại phí ship"]},
                )
            )
        ]
    )


def test_fr_rep_04_ai_draft_requires_approval(client: Any, cube: Any, session: Any) -> None:  # noqa: F811
    from app.ask.agents import run_agents
    from app.db.models import Notification, Report

    rid = _build(client)["report_id"]
    fm = _insight_model()
    assert run_agents(session, caller=fm) == {"insight_drafts": 1, "triage": 0}
    session.commit()
    # Chỉ gửi snapshot (số tổng hợp), playbook và nhật ký quyết định.
    payload = json.loads(fm.calls[0][1][0]["content"])
    assert set(payload) == {"tenant", "pack", "period", "data_stale", "snapshot", "decisions"}
    assert "Playbook" in fm.calls[0][0]

    r = client.get(f"/v1/reports/{rid}", headers=auth("data_lead", "demo_seller")).json()
    assert r["insight_draft_md"] == DRAFT and r["actions_draft"] == [
        "Nhập giá vốn cho 2 SKU còn thiếu",
        "Xem lại phí ship",
    ]
    assert r["status"] == "draft" and not r["insight_md"]
    # Khách không thấy bản nháp; chưa duyệt thì không có tin nào gửi đi.
    assert client.get(f"/v1/reports/{rid}", headers=auth("owner_seller", "demo_seller")).status_code == 404
    assert session.scalars(select(Notification).where(Notification.template.like("report%"))).all() == []
    # Có bản nháp AI nhưng nhận định chính thức trống → không duyệt được.
    ap = client.post(f"/v1/reports/{rid}/approve", headers=auth("data_lead"))
    assert ap.status_code == 422 and ap.json()["code"] == "INSIGHT_REQUIRED"
    # Lần chạy sau không dựng lại bản nháp đã có.
    assert run_agents(session, caller=FakeModel([])) == {"insight_drafts": 0, "triage": 0}
    # Dựng lại báo cáo thì bản nháp AI được làm mới theo snapshot mới.
    _build(client)
    session.expire_all()
    assert session.get(Report, rid).insight_draft_md is None


def test_weekly_insight_failure_marks_attempt(client: Any, cube: Any, session: Any) -> None:  # noqa: F811
    from app.ask.agents import run_agents
    from app.db.models import Report

    rid = _build(client)["report_id"]
    bad = FakeModel([{"content": [{"type": "text", "text": ""}], "usage": {}}])
    assert run_agents(session, caller=bad)["insight_drafts"] == 0
    session.commit()
    r = session.get(Report, rid)
    assert r.insight_draft_md is None and r.actions_draft == []


def test_incident_triage(client: Any, session: Any) -> None:
    from app.ask.agents import run_agents
    from app.db.models import PipelineRun

    body = {
        "run_id": "run-x",
        "tenant_id": "demo_seller",
        "job": "tenant_pipeline",
        "status": "blocked",
        "failed_step": "dbt_test",
        "blocking_failures": [{"test": "not_null_fct_orders_order_id", "rows": [{"phone": "0909123456"}]}],
    }
    assert client.post("/v1/internal/runs", json=body, headers=INTERNAL).status_code == 204
    fm = FakeModel([reply(tool_use(1, "triage", {"triage_md": "**Nguyên nhân khả nghi:** đơn thiếu mã."}))])
    assert run_agents(session, caller=fm) == {"insight_drafts": 0, "triage": 1}
    session.commit()
    sent = fm.calls[0][1][0]["content"]
    assert "0909123456" not in sent and "not_null_fct_orders_order_id" in sent
    run = session.get(PipelineRun, "run-x")
    assert run.triage_md.startswith("**Nguyên nhân")
    runs = client.get("/v1/ops/tenants/demo_seller/runs", headers=auth("data_lead")).json()
    assert runs[0]["triage_md"].startswith("**Nguyên nhân")


def test_agents_skip_without_key(client: Any, session: Any) -> None:
    from app.ask.agents import run_agents

    assert run_agents(session) == {}
