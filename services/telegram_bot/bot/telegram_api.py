"""Gọi Telegram Bot API qua httpx (spec 08 §1). Không log nội dung tin."""

from __future__ import annotations

import html
from typing import Any

import httpx

from dx_common.config import get_settings
from dx_common.logging import get_logger

log = get_logger(__name__)
MAX_LEN = 4096
COMMANDS = [
    {"command": "week", "description": "Ba số chính của tuần này"},
    {"command": "month", "description": "Ba số chính của tháng này"},
    {"command": "report", "description": "Báo cáo tuần mới nhất"},
    {"command": "unlink", "description": "Gỡ liên kết chat này"},
    {"command": "help", "description": "Danh sách lệnh"},
]


class BotApiError(Exception):
    def __init__(self, method: str, code: int, description: str) -> None:
        super().__init__(f"{method}: {code}")
        self.method, self.code, self.description = method, code, description


def split_html(text: str, limit: int = MAX_LEN) -> list[str]:
    """Chia tin dài theo dòng để mỗi phần ≤ 4096 ký tự (spec 08 §1 `send.py`)."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    cur = ""
    for line in text.split("\n"):
        while len(line) > limit:  # một dòng quá dài: cắt cứng
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(line[:limit])
            line = line[limit:]
        candidate = f"{cur}\n{line}" if cur else line
        if len(candidate) > limit:
            parts.append(cur)
            cur = line
        else:
            cur = candidate
    if cur:
        parts.append(cur)
    return parts


def keyboard(buttons: list[dict[str, Any]]) -> dict[str, Any] | None:
    rows = []
    for b in buttons or []:
        btn: dict[str, Any] = {"text": b["label"]}
        if b.get("url"):
            btn["url"] = b["url"]
        elif b.get("callback_data"):
            btn["callback_data"] = b["callback_data"]
        else:
            continue
        rows.append([btn])
    return {"inline_keyboard": rows} if rows else None


class TelegramApi:
    def __init__(
        self, token: str | None = None, base: str | None = None, client: httpx.AsyncClient | None = None
    ) -> None:
        s = get_settings()
        self.token = token or s.telegram_bot_token
        self.base = (base or s.telegram_api_base).rstrip("/")
        self.client = client or httpx.AsyncClient(timeout=30)

    async def call(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        r = await self.client.post(f"{self.base}/bot{self.token}/{method}", json=payload or {})
        body = r.json() if r.content else {}
        if not body.get("ok"):
            log.warning("Bot API lỗi", extra={"method": method, "code": body.get("error_code", r.status_code)})
            raise BotApiError(method, int(body.get("error_code") or r.status_code), str(body.get("description", "")))
        return body.get("result")

    async def send(self, chat_id: int, text_html: str, buttons: list[dict[str, Any]] | None = None) -> None:
        parts = split_html(text_html)
        for i, part in enumerate(parts):
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "text": part,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            kb = keyboard(buttons or []) if i == len(parts) - 1 else None
            if kb:
                payload["reply_markup"] = kb
            await self.call("sendMessage", payload)

    async def typing(self, chat_id: int) -> None:
        await self.call("sendChatAction", {"chat_id": chat_id, "action": "typing"})

    async def answer_callback(self, callback_id: str, text: str | None = None) -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_id}
        if text:
            payload["text"] = text
        await self.call("answerCallbackQuery", payload)

    async def setup_webhook(self, url: str, secret: str) -> None:
        await self.call(
            "setWebhook",
            {"url": url, "secret_token": secret, "allowed_updates": ["message", "callback_query", "my_chat_member"]},
        )
        await self.call("setMyCommands", {"commands": COMMANDS})

    async def get_me(self) -> dict[str, Any]:
        return dict(await self.call("getMe"))

    async def get_updates(self, offset: int | None, timeout: int = 30) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query", "my_chat_member"],
        }
        if offset is not None:
            payload["offset"] = offset
        return list(await self.call("getUpdates", payload) or [])


def escape(s: str) -> str:
    return html.escape(s, quote=False)
