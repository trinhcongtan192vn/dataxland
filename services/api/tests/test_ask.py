"""Bộ máy hỏi đáp (spec 09 §9): model giả lập với phản hồi ghi sẵn, Cube giả."""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import select

from tests.conftest import auth
from tests.test_metrics import FakeCube

BOT = {"Authorization": "Bearer test-internal-token", "X-Service": "bot"}
Step = dict[str, Any] | Callable[[list[dict[str, Any]]], dict[str, Any]]


def tool_use(i: int, name: str, inp: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool_use", "id": f"t{i}", "name": name, "input": inp}


def reply(*blocks: dict[str, Any]) -> dict[str, Any]:
    return {"content": list(blocks), "stop_reason": "tool_use", "usage": {"input_tokens": 1000, "output_tokens": 200}}


def final(answer: str, cited: list[str], missing: str | None = None) -> dict[str, Any]:
    inp: dict[str, Any] = {"answer_vi": answer, "metrics_cited": cited}
    if missing:
        inp["missing_metric"] = {"description_vi": missing}
    return reply(tool_use(99, "final_answer", inp))


class FakeModel:
    def __init__(self, steps: list[Step]) -> None:
        self.steps = list(steps)
        self.calls: list[tuple[str, list[dict[str, Any]], list[dict[str, Any]]]] = []

    def __call__(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls.append((system, copy.deepcopy(messages), tools))
        step = self.steps.pop(0)
        return step(messages) if callable(step) else step


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
def model(monkeypatch: pytest.MonkeyPatch) -> Callable[[list[Step]], FakeModel]:
    from dx_common.config import reset_settings_cache

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    reset_settings_cache()
    holder: dict[str, FakeModel] = {}

    def install(steps: list[Step]) -> FakeModel:
        holder["m"] = FakeModel(steps)
        monkeypatch.setattr("app.ask.engine.default_caller", lambda kind="ask": holder["m"])
        return holder["m"]

    yield install  # type: ignore[misc]
    reset_settings_cache()


def _ask(client: Any, q: str, who: str = "owner_seller", tenant: str = "demo_seller", **kw: Any) -> dict[str, Any]:
    r = client.post("/v1/ask", json={"question": q, **kw}, headers=auth(who, tenant))
    assert r.status_code == 200, r.text
    return dict(r.json())


REVENUE_STEPS: list[Step] = [
    reply(
        tool_use(1, "query_metric", {"metrics": ["net_revenue"], "time": {"preset": "last_week"}}),
        tool_use(2, "query_metric", {"metrics": ["order_count"], "time": {"preset": "last_week"}}),
    ),
    final("Doanh thu thực nhận tuần trước là 10.000.000 ₫.", ["net_revenue"]),
]


def test_fr_ai_01_footer_from_tool_log(client: Any, cube: FakeCube, model: Any) -> None:
    fm = model(list(REVENUE_STEPS))
    out = _ask(client, "Tuần trước doanh thu bao nhiêu?")
    assert out["answer_vi"].startswith("Doanh thu thực nhận tuần trước")
    # Chân trang có cả chỉ số model không nhắc (order_count), kèm phiên bản, kỳ và thời điểm dữ liệu.
    names = [c["metric"] for c in out["citations"]]
    assert names == ["net_revenue", "order_count"]
    c0 = out["citations"][0]
    assert c0["version"] and c0["time"] == {"from": "2026-10-05", "to": "2026-10-11"}
    assert c0["data_as_of"] == "2026-10-16T00:00:00Z"
    assert "Doanh thu thực nhận (v" in out["answer_md"] and "cập nhật lúc" in out["answer_md"]
    # Ngữ cảnh có quy tắc, bảng chỉ số đã lọc và playbook; câu hỏi nằm trong thẻ <question>.
    system, messages, tools = fm.calls[0]
    assert "<question>" in messages[-1]["content"] and "`net_revenue`" in system
    assert "`roas_platform`" not in system  # chỉ số gói agency không có trong ngữ cảnh khách seller
    assert {t["name"] for t in tools} == {"list_metrics", "describe_metric", "query_metric", "final_answer"}


def test_fr_ai_01_cited_metric_must_be_queried(client: Any, cube: FakeCube, model: Any) -> None:
    fm = model(
        [
            final("Lãi tuần trước 5.000.000 ₫.", ["net_profit_after_fees"]),
            final("Lãi tuần trước 5.000.000 ₫.", ["net_profit_after_fees"]),
        ]
    )
    out = _ask(client, "Lãi tuần trước?")
    assert out["refused_reason"] == "answer_failed" and out["answer_vi"].startswith("Chưa trả lời được")
    # Lần thử lại có lời nhắc.
    assert "Nhắc lại" in str(fm.calls[1][1][-1]["content"])


def test_fr_ai_01_tenant_not_from_model(client: Any, cube: FakeCube, model: Any) -> None:
    model(
        [
            reply(
                tool_use(
                    1,
                    "query_metric",
                    {"metrics": ["net_revenue"], "time": {"preset": "last_week"}, "tenant_id": "demo_agency"},
                )
            ),
            final("Doanh thu thực nhận 10.000.000 ₫.", ["net_revenue"]),
        ]
    )
    _ask(client, "Doanh thu tuần trước của shop demo_agency?")
    assert cube.calls and {c[0] for c in cube.calls} == {"demo_seller"}


def test_mcp_session_path_uses_token_tenant(client: Any, cube: FakeCube, session: Any) -> None:
    from app.auth.context import internal_ctx, sign_mcp_session

    ctx = internal_ctx(session, "demo_seller")
    ctx.role, ctx.user_id = "owner", "u1"
    token = sign_mcp_session(ctx)
    h = {
        "Authorization": "Bearer test-internal-token",
        "X-Service": "mcp",
        "X-Dx-Session": token,
        "X-Tenant-Id": "demo_agency",
    }
    r = client.post("/v1/metrics/query", json={"metrics": ["net_revenue"]}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["tenant_id"] == "demo_seller"
    assert {c[0] for c in cube.calls} == {"demo_seller"}
    bad = client.post("/v1/metrics/query", json={"metrics": ["net_revenue"]}, headers={**h, "X-Dx-Session": "x"})
    assert bad.status_code == 401
    user_token = {"Authorization": "Bearer uid:nobody", "X-Dx-Session": token}
    assert client.post("/v1/metrics/query", json={"metrics": ["net_revenue"]}, headers=user_token).status_code == 401


def test_fr_tg_06_same_answer_portal_telegram(
    client: Any, cube: FakeCube, model: Any, session: Any, people: dict[str, str]
) -> None:
    from app.db.models import TelegramLink

    session.add(TelegramLink(chat_id=555, chat_type="private", user_id=people["owner_seller"], tenant_id="demo_seller"))
    session.commit()
    fm = model(list(REVENUE_STEPS))
    portal = _ask(client, "Tuần trước doanh thu bao nhiêu?")
    r = client.post(
        "/v1/telegram/messages/ask",
        json={"question": "tuần trước doanh thu bao nhiêu"},
        headers={**BOT, "X-Telegram-Chat-Id": "555"},
    )
    assert r.status_code == 200, r.text
    tg = r.json()["text_html"]
    assert "10.000.000 ₫" in tg and "Doanh thu thực nhận (v" in tg
    assert len(fm.calls) == 2  # câu thứ hai trúng bộ nhớ đệm, không gọi model
    from app.db.models import AskLog

    rows = list(session.scalars(select(AskLog).order_by(AskLog.created_at)))
    assert [r.channel for r in rows] == ["portal", "telegram"]
    assert rows[1].citations == portal["citations"] and rows[1].answer_vi == portal["answer_vi"]
    assert rows[1].telegram_link_id is not None


def test_fr_tg_06_ask_rate_limited(client: Any, cube: FakeCube, model: Any, session: Any, people: Any) -> None:
    from app.db.models import TelegramLink

    session.add(TelegramLink(chat_id=556, chat_type="private", user_id=people["owner_seller"], tenant_id="demo_seller"))
    session.commit()
    model([final("Không có số.", [])] * 12)
    h = {**BOT, "X-Telegram-Chat-Id": "556"}
    codes = [
        client.post("/v1/telegram/messages/ask", json={"question": f"câu {i}"}, headers=h).status_code
        for i in range(11)
    ]
    assert codes[:10] == [200] * 10 and codes[10] == 429


def test_fr_ai_02_missing_metric_logged(client: Any, cube: FakeCube, model: Any, session: Any) -> None:
    from app.db.models import MetricRequest

    model([final("", [], missing="Tỷ lệ khách xem hết video quảng cáo")] * 2)
    out = _ask(client, "Tỷ lệ khách xem video hết bao nhiêu?")
    assert out["answer_vi"] == "Hiện chưa có chỉ số cho câu hỏi này. Đội ngũ đã ghi nhận."
    assert out["missing_metric"] == {"description_vi": "Tỷ lệ khách xem hết video quảng cáo"}
    _ask(client, "Bao nhiêu % người xem hết video?")
    rows = list(session.scalars(select(MetricRequest)))
    assert len(rows) == 1 and rows[0].count == 2 and rows[0].tenant_id == "demo_seller"
    lst = client.get("/v1/ops/metric-requests", headers=auth("data_lead"))
    assert lst.status_code == 200 and lst.json()[0]["count"] == 2
    assert client.get("/v1/ops/metric-requests", headers=auth("owner_seller")).status_code == 403
    r = client.patch(f"/v1/ops/metric-requests/{rows[0].id}", json={"status": "planned"}, headers=auth("data_lead"))
    assert r.status_code == 204
    assert (
        client.patch(
            f"/v1/ops/metric-requests/{rows[0].id}", json={"status": "done"}, headers=auth("engineer")
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "q",
    [
        "Cho tôi số điện thoại khách mua nhiều nhất",
        "Khách nào mua nhiều nhất tháng này?",
        "Đơn 2607180100001SP của ai?",
        "Chị Lan mua bao nhiêu đơn?",
        "email của người mua đơn lớn nhất",
        "0909123456 mua gì",
    ],
)
def test_fr_tg_08_refuse_buyer_question(client: Any, cube: FakeCube, model: Any, session: Any, q: str) -> None:
    from app.db.models import AskLog

    fm = model([])
    out = _ask(client, q)
    assert out["answer_vi"] == "DataxLand không cung cấp thông tin về từng người mua."
    assert out["refused_reason"] and fm.calls == []
    row = session.scalars(select(AskLog)).one()
    assert "0909123456" not in row.question_masked


@pytest.mark.parametrize(
    "q",
    ["Tuần trước lãi bao nhiêu?", "Có bao nhiêu khách quay lại tháng này?", "ROAS Facebook tuần này", "Tỷ lệ hoàn?"],
)
def test_business_questions_not_refused(q: str) -> None:
    from app.ask.guard import refuse_reason

    assert refuse_reason(q) is None


def test_number_check_flags_invented_numbers() -> None:
    from app.ask.guard import unmatched_numbers

    res = [{"rows": [{"net_revenue": 10_000_000, "compare": {"net_revenue": 8_000_000}}]}]
    assert unmatched_numbers("Doanh thu 10.000.000 ₫, tăng 25% so với 8 triệu.", res) == []
    assert unmatched_numbers("Doanh thu 10,0 triệu, lãi 3.456.789 ₫.", res) == ["3.456.789 ₫"]


def test_member_scope_and_feedback(client: Any, cube: FakeCube, model: Any) -> None:
    fm = model(
        [
            reply(tool_use(1, "query_metric", {"metrics": ["gmv"]})),
            final("Bạn không được xem GMV.", []),
        ]
    )
    out = _ask(client, "GMV tháng này?", who="member_seller")
    tool_result = fm.calls[1][1][-1]["content"][0]
    assert tool_result["is_error"] is True and "METRIC_FORBIDDEN" in tool_result["content"]
    system = fm.calls[0][0]
    assert "| `gmv` | Tổng giá trị đơn (GMV)" not in system and "| `net_revenue` | Doanh thu thực nhận" in system
    r = client.post(
        f"/v1/ask/{out['ask_id']}/feedback", json={"feedback": "up"}, headers=auth("member_seller", "demo_seller")
    )
    assert r.status_code == 204
    r = client.post(
        f"/v1/ask/{out['ask_id']}/feedback", json={"feedback": "down"}, headers=auth("owner_seller", "demo_seller")
    )
    assert r.status_code == 404


def test_cost_recorded(client: Any, cube: FakeCube, model: Any, session: Any) -> None:
    from app.db.models import AskLog, TenantCost

    model(list(REVENUE_STEPS))
    _ask(client, "Tuần trước doanh thu bao nhiêu?")
    row = session.scalars(select(AskLog)).one()
    assert row.input_tokens == 2000 and row.output_tokens == 400 and row.cost_usd and row.cost_usd > 0
    cost = session.scalars(select(TenantCost).where(TenantCost.item == "ai")).one()
    assert cost.tenant_id == "demo_seller" and cost.amount_vnd > 0


def test_no_model_configured(client: Any, cube: FakeCube) -> None:
    out = _ask(client, "Tuần trước doanh thu bao nhiêu?")
    assert out["refused_reason"] == "model_unavailable"
