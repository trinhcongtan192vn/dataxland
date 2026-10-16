"""Telegram phía API (spec 08 §9): FR-TG-01..05, FR-TG-07, tách biệt khách."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest

from tests.conftest import FakeChannel, auth
from tests.test_metrics import FakeCube
from tests.test_notify import _run

CHAT, GROUP = 555001, -100777


def bot(chat: int) -> dict[str, str]:
    return {"Authorization": "Bearer test-internal-token", "X-Service": "bot", "X-Telegram-Chat-Id": str(chat)}


@pytest.fixture()
def cube(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeCube]:
    from app.metrics.cube_client import set_cube

    monkeypatch.setenv("DX_TODAY", "2026-10-16")
    monkeypatch.setenv("DX_NOW", "2026-10-16T03:00:00Z")
    fake = FakeCube()
    set_cube(fake)
    yield fake
    set_cube(None)


def _code(client: Any, key: str, tenant: str, kind: str = "private", scope: list[str] | None = None) -> Any:
    body: dict[str, Any] = {"kind": kind}
    if scope is not None:
        body["metric_scope"] = scope
    return client.post("/v1/telegram/link-codes", json=body, headers=auth(key, tenant))


def _link(client: Any, code: str, chat: int = CHAT, chat_type: str = "private") -> dict[str, Any]:
    r = client.post(
        "/v1/telegram/links",
        json={"code": code, "chat_id": chat, "chat_type": chat_type, "telegram_user_id": 42},
        headers=bot(chat),
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


def test_fr_tg_01_link_with_valid_code(client: Any, session: Any) -> None:
    c = _code(client, "owner_seller", "demo_seller").json()
    assert len(c["code"]) == 8 and c["deep_link"].endswith(f"?start={c['code']}")
    res = _link(client, c["code"])
    assert res["ok"] and "Đã liên kết với <b>Shop Demo</b>" in res["message"]["text_html"]
    from sqlalchemy import text

    n = session.execute(text("select count(*) from events where type = 'telegram.linked'")).scalar()
    assert n == 1
    links = client.get("/v1/telegram/links", headers=auth("owner_seller", "demo_seller")).json()
    assert len(links) == 1 and links[0]["chat_type"] == "private"


def test_fr_tg_01_code_used_or_expired(client: Any, session: Any) -> None:
    c = _code(client, "owner_seller", "demo_seller").json()
    assert _link(client, c["code"])["ok"]
    again = _link(client, c["code"], chat=CHAT + 1)
    assert again["error_code"] == "CODE_EXPIRED"
    from app.db.models import TelegramLinkCode

    c2 = _code(client, "owner_seller", "demo_seller").json()
    for row in session.query(TelegramLinkCode).filter(TelegramLinkCode.used_at.is_(None)):
        row.expires_at = row.expires_at - timedelta(minutes=11)
    session.commit()
    assert _link(client, c2["code"], chat=CHAT + 2)["error_code"] == "CODE_EXPIRED"
    assert _link(client, "ZZZZZZZZ", chat=CHAT + 3)["error_code"] == "CODE_INVALID"


def test_bad_code_lockout(client: Any) -> None:
    for _ in range(5):
        assert _link(client, "WRONGCODE", chat=CHAT)["error_code"] == "CODE_INVALID"
    good = _code(client, "owner_seller", "demo_seller").json()["code"]
    assert _link(client, good, chat=CHAT)["error_code"] == "LOCKED"


def test_fr_tg_01_unlinked_chat_gets_no_numbers(client: Any, cube: FakeCube) -> None:
    r = client.post("/v1/telegram/messages/key_numbers", json={"period": "this_week"}, headers=bot(CHAT))
    assert r.status_code == 200
    assert "chưa liên kết" in r.json()["text_html"] and "₫" not in r.json()["text_html"]
    assert cube.calls == []


def test_fr_tg_03_week_matches_portal(client: Any, cube: FakeCube) -> None:
    _link(client, _code(client, "owner_seller", "demo_seller").json()["code"])
    msg = client.post("/v1/telegram/messages/key_numbers", json={"period": "this_week"}, headers=bot(CHAT)).json()
    portal = client.get("/v1/metrics/key-numbers?period=this_week", headers=auth("owner_seller", "demo_seller")).json()
    from app.notify.render import f_unit

    first = portal["numbers"][0]
    assert f_unit(first["value"], first["unit"]) in msg["text_html"]
    assert "Tuần này (12/10–15/10)" in msg["text_html"] and "Cập nhật lúc" in msg["text_html"]
    assert msg["buttons"][0]["url"].startswith("https://app.test/app/dashboards/seller")


def test_fr_tg_04_unlink_then_not_linked(client: Any, cube: FakeCube) -> None:
    _link(client, _code(client, "owner_seller", "demo_seller").json()["code"])
    confirm = client.post("/v1/telegram/messages/unlink_confirm", json={}, headers=bot(CHAT)).json()
    assert confirm["buttons"][0]["callback_data"] == "ku:demo_seller"
    r = client.post("/v1/telegram/unlink", json={"tenant_id": "demo_seller"}, headers=bot(CHAT))
    assert r.json()["unlinked"] == 1
    after = client.post("/v1/telegram/messages/key_numbers", json={}, headers=bot(CHAT)).json()
    assert "chưa liên kết" in after["text_html"]


def test_fr_tg_04_access_lost_unlinks(client: Any, cube: FakeCube, people: dict[str, str]) -> None:
    _link(client, _code(client, "member_seller", "demo_seller").json()["code"])
    r = client.delete(f"/v1/members/{people['member_seller']}", headers=auth("owner_seller", "demo_seller"))
    assert r.status_code == 204
    after = client.post("/v1/telegram/messages/key_numbers", json={}, headers=bot(CHAT)).json()
    assert "chưa liên kết" in after["text_html"]


def test_fr_tg_05_group_code_owner_only(client: Any) -> None:
    r = _code(client, "member_seller", "demo_seller", "group", ["net_revenue"])
    assert r.status_code == 403
    assert _code(client, "owner_seller", "demo_seller", "group", []).status_code == 422
    assert _code(client, "owner_seller", "demo_seller", "group", ["orders_placed"]).status_code == 422


def test_fr_tg_05_group_scope(client: Any, cube: FakeCube) -> None:
    c = _code(client, "owner_seller", "demo_seller", "group", ["net_revenue"]).json()
    assert "startgroup=" in c["deep_link"]
    assert _link(client, c["code"], chat=CHAT, chat_type="private")["error_code"] == "CODE_WRONG_CHAT_TYPE"
    c = _code(client, "owner_seller", "demo_seller", "group", ["net_revenue"]).json()
    assert _link(client, c["code"], chat=GROUP, chat_type="supergroup")["ok"]
    msg = client.post("/v1/telegram/messages/key_numbers", json={}, headers=bot(GROUP)).json()["text_html"]
    assert "Doanh thu thực nhận: 10.000.000 ₫" in msg
    assert "Lãi sau phí: — (ngoài phạm vi của nhóm)" in msg


def test_fr_tg_07_rate_limit(client: Any, cube: FakeCube) -> None:
    _link(client, _code(client, "owner_seller", "demo_seller").json()["code"])
    for _ in range(20):
        assert client.post("/v1/telegram/messages/key_numbers", json={}, headers=bot(CHAT)).status_code == 200
    r = client.post("/v1/telegram/messages/key_numbers", json={}, headers=bot(CHAT))
    assert r.status_code == 429
    assert "thử lại sau" in r.json()["message"]["text_html"]


def test_choose_tenant_when_many(client: Any, cube: FakeCube, session: Any, people: dict[str, str]) -> None:
    from app.db.models import Membership

    session.add(Membership(user_id=people["owner_seller"], tenant_id="demo_agency", role="owner"))
    session.commit()
    _link(client, _code(client, "owner_seller", "demo_seller").json()["code"])
    _link(client, _code(client, "owner_seller", "demo_agency").json()["code"])
    msg = client.post("/v1/telegram/messages/key_numbers", json={"period": "this_month"}, headers=bot(CHAT)).json()
    assert {b["callback_data"] for b in msg["buttons"]} == {"kt:month:demo_seller", "kt:month:demo_agency"}
    one = client.post(
        "/v1/telegram/messages/key_numbers",
        json={"period": "this_month", "tenant_id": "demo_agency"},
        headers=bot(CHAT),
    ).json()
    assert "Chi phí quảng cáo" in one["text_html"]


def test_isolation_telegram(client: Any, cube: FakeCube) -> None:
    _link(client, _code(client, "owner_seller", "demo_seller").json()["code"])
    r = client.post("/v1/telegram/messages/key_numbers", json={"tenant_id": "demo_agency"}, headers=bot(CHAT)).json()
    assert "chưa liên kết" in r["text_html"]
    assert all(t == "demo_seller" for t, _, _ in cube.calls)


def test_fr_tg_02_report_ready_delivered(
    client: Any, cube: FakeCube, session: Any, channels: dict[str, FakeChannel]
) -> None:
    from tests.test_reports import _build

    _link(client, _code(client, "owner_seller", "demo_seller").json()["code"])
    rid = _build(client)["report_id"]
    lead = auth("data_lead")
    client.put(f"/v1/reports/{rid}", json={"insight_md": "ok"}, headers=lead)
    client.post(f"/v1/reports/{rid}/approve", headers=lead)
    _run(session)
    tg = [(r, m) for r, m in channels["telegram"].sent if m.template == "report_ready"]
    assert tg and tg[0][0].address == str(CHAT)
    assert tg[0][1].buttons[0].label == "Xem báo cáo" and "/r/" in (tg[0][1].buttons[0].url or "")
    latest = client.post("/v1/telegram/messages/latest_report", json={}, headers=bot(CHAT)).json()
    assert "Báo cáo tuần 41" in latest["text_html"]
    url = latest["buttons"][0]["url"]
    o = client.get(url.replace("https://app.test", ""), follow_redirects=False)
    assert o.status_code == 302 and f"/app/reports/{rid}" in o.headers["location"]


def test_bot_endpoints_require_bot_service(client: Any) -> None:
    h = bot(CHAT) | {"X-Service": "dagster"}
    assert client.post("/v1/telegram/messages/help", json={}, headers=h).status_code == 403
    assert client.post("/v1/telegram/messages/help", json={}, headers=auth("owner_seller")).status_code in (401, 403)
