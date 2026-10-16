"""Dịch vụ bot với Bot API và services/api giả lập (spec 08 §9)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

TG = "https://tg.test"
API = "http://api.test"
SECRET = "test-webhook-secret"


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    from dx_common.config import reset_settings_cache

    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "dataxland_bot")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_API_BASE", TG)
    monkeypatch.setenv("API_INTERNAL_URL", API)
    monkeypatch.setenv("INTERNAL_API_TOKEN", "tok")
    monkeypatch.setenv("BOT_MODE", "webhook")
    monkeypatch.setenv("BOT_PUBLIC_URL", "")
    reset_settings_cache()
    from bot.main import create_app

    sent: list[dict[str, Any]] = []
    api_calls: list[tuple[str, dict[str, Any], str | None]] = []
    state: dict[str, Any] = {"tg_status": 200, "api": {}}

    def tg_handler(request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[1]
        body = json.loads(request.content or b"{}")
        if method == "sendMessage":
            if state["tg_status"] != 200:
                return httpx.Response(
                    403, json={"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked"}
                )
            sent.append(body)
        if method == "getMe":
            return httpx.Response(200, json={"ok": True, "result": {"id": 1, "username": "dataxland_bot"}})
        return httpx.Response(200, json={"ok": True, "result": True})

    def api_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        api_calls.append((request.url.path, body, request.headers.get("X-Telegram-Chat-Id")))
        assert request.headers["Authorization"] == "Bearer tok" and request.headers["X-Service"] == "bot"
        override = state["api"].get(request.url.path)
        if override:
            return override
        return httpx.Response(200, json={"text_html": f"tin cho {request.url.path}", "buttons": []})

    with respx.mock(assert_all_called=False) as m:
        m.route(host="tg.test").mock(side_effect=tg_handler)
        m.route(host="api.test").mock(side_effect=api_handler)
        with TestClient(create_app(setup=False)) as client:
            yield {"client": client, "sent": sent, "api": api_calls, "state": state}
    reset_settings_cache()


def post(env: dict[str, Any], update: dict[str, Any], secret: str | None = SECRET) -> httpx.Response:
    h = {"X-Telegram-Bot-Api-Secret-Token": secret} if secret else {}
    return env["client"].post("/tg/webhook", json=update, headers=h)


def msg(text: str, chat_id: int = 111, chat_type: str = "private") -> dict[str, Any]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "chat": {"id": chat_id, "type": chat_type, "title": "Nhóm"},
            "from": {"id": 42},
            "text": text,
        },
    }


def test_webhook_secret_required(env: dict[str, Any]) -> None:
    assert post(env, msg("/week"), secret=None).status_code == 401
    assert post(env, msg("/week"), secret="sai").status_code == 401
    assert env["api"] == [] and env["sent"] == []


def test_fr_tg_01_start_with_code_links(env: dict[str, Any]) -> None:
    env["state"]["api"]["/v1/telegram/links"] = httpx.Response(
        200, json={"ok": True, "message": {"text_html": "✅ Đã liên kết", "buttons": []}}
    )
    assert post(env, msg("/start ABCD2345")).status_code == 200
    path, body, chat = env["api"][0]
    assert path == "/v1/telegram/links" and body["code"] == "ABCD2345" and body["chat_type"] == "private"
    assert body["telegram_user_id"] == 42 and chat == "111"
    assert env["sent"][0]["text"] == "✅ Đã liên kết" and env["sent"][0]["parse_mode"] == "HTML"


def test_fr_tg_03_commands_route_to_api(env: dict[str, Any]) -> None:
    post(env, msg("/week"))
    post(env, msg("/month@dataxland_bot", chat_id=-100, chat_type="supergroup"))
    post(env, msg("/report"))
    post(env, msg("/week@other_bot", chat_id=-100, chat_type="supergroup"))
    calls = [(p, b) for p, b, _ in env["api"]]
    assert calls == [
        ("/v1/telegram/messages/key_numbers", {"period": "this_week", "command": "week"}),
        ("/v1/telegram/messages/key_numbers", {"period": "this_month", "command": "month"}),
        ("/v1/telegram/messages/latest_report", {"command": "report"}),
    ]
    assert len(env["sent"]) == 3


def test_buttons_rendered_as_inline_keyboard(env: dict[str, Any]) -> None:
    env["state"]["api"]["/v1/telegram/messages/key_numbers"] = httpx.Response(
        200,
        json={
            "text_html": "Số",
            "buttons": [
                {"label": "Mở dashboard", "url": "https://app.test/x"},
                {"label": "Shop A", "callback_data": "kt:week:a"},
            ],
        },
    )
    post(env, msg("/week"))
    kb = env["sent"][0]["reply_markup"]["inline_keyboard"]
    assert kb == [
        [{"text": "Mở dashboard", "url": "https://app.test/x"}],
        [{"text": "Shop A", "callback_data": "kt:week:a"}],
    ]


def test_callback_runs_command_for_tenant(env: dict[str, Any]) -> None:
    cb = {
        "update_id": 2,
        "callback_query": {
            "id": "cb1",
            "data": "kt:week:demo_seller",
            "message": {"chat": {"id": 111, "type": "private"}},
        },
    }
    post(env, cb)
    assert env["api"][0][1] == {"tenant_id": "demo_seller", "period": "this_week", "command": "week"}
    unlink = {
        "update_id": 3,
        "callback_query": {"id": "cb2", "data": "ku:*", "message": {"chat": {"id": 111, "type": "private"}}},
    }
    post(env, unlink)
    assert env["api"][1][:2] == ("/v1/telegram/unlink", {"tenant_id": None})


def test_fr_tg_06_free_text_gets_help(env: dict[str, Any]) -> None:
    post(env, msg("doanh thu hôm qua bao nhiêu?"))
    assert env["api"][0][:2] == ("/v1/telegram/messages/help", {"free_text": True})
    post(env, msg("chào cả nhóm", chat_id=-100, chat_type="group"))
    assert len(env["api"]) == 1


def test_fr_tg_07_rate_limited_message_sent(env: dict[str, Any]) -> None:
    env["state"]["api"]["/v1/telegram/messages/key_numbers"] = httpx.Response(
        429,
        json={
            "code": "RATE_LIMITED",
            "message": {"text_html": "Bạn thao tác hơi nhanh, thử lại sau 3 phút.", "buttons": []},
        },
    )
    post(env, msg("/week"))
    assert "thử lại sau 3 phút" in env["sent"][0]["text"]


def test_not_linked_on_403(env: dict[str, Any]) -> None:
    env["state"]["api"]["/v1/telegram/messages/key_numbers"] = httpx.Response(403, json={"code": "TELEGRAM_NOT_LINKED"})
    post(env, msg("/week"))
    assert env["api"][1][0] == "/v1/telegram/messages/not_linked"


def test_fr_tg_04_bot_removed_or_blocked(env: dict[str, Any]) -> None:
    upd = {
        "update_id": 4,
        "my_chat_member": {"chat": {"id": -100, "type": "supergroup"}, "new_chat_member": {"status": "left"}},
    }
    post(env, upd)
    assert env["api"][0][:2] == ("/v1/telegram/chat-left", {"chat_id": -100, "reason": "bot_removed"})
    env["state"]["tg_status"] = 403
    post(env, msg("/week"))
    assert env["api"][-1][:2] == ("/v1/telegram/chat-left", {"chat_id": 111, "reason": "bot_blocked"})


def test_healthz_calls_get_me(env: dict[str, Any]) -> None:
    r = env["client"].get("/healthz")
    assert r.json() == {"status": "ok", "username": "dataxland_bot"}


def test_split_long_message() -> None:
    from bot.telegram_api import split_html

    text = "\n".join(f"dòng {i} " + "x" * 90 for i in range(100))
    parts = split_html(text)
    assert len(parts) > 1 and all(len(p) <= 4096 for p in parts)
    assert "\n".join(parts) == text
