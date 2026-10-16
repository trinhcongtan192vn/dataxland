"""Xử lý cập nhật Telegram (spec 08 §3–§5). Bot không có logic nghiệp vụ: mọi tin do API dựng.

| Cập nhật | Việc |
|---|---|
| `/start <mã>` | Đổi mã lấy liên kết |
| `/week`, `/month`, `/report`, `/help`, `/unlink` | Gọi `POST /v1/telegram/messages/<kind>` |
| Nút `kt:<lệnh>:<khách>` | Chạy lệnh cho khách đã chọn (chat liên kết nhiều khách) |
| Nút `ku:<khách>` / `ku:*` | Gỡ liên kết sau khi xác nhận |
| Tin tự do trong chat riêng | GĐ1: trả `help` kèm ghi chú; không gọi AI |
| `my_chat_member` bị xóa/chặn | `POST /v1/telegram/chat-left` |
"""

from __future__ import annotations

import hashlib
from typing import Any

from bot.api_client import ApiResult, BotApiClient
from bot.telegram_api import BotApiError, TelegramApi
from dx_common.logging import get_logger

log = get_logger(__name__)

COMMANDS: dict[str, tuple[str, dict[str, Any]]] = {
    "week": ("key_numbers", {"period": "this_week", "command": "week"}),
    "month": ("key_numbers", {"period": "this_month", "command": "month"}),
    "report": ("latest_report", {"command": "report"}),
    "help": ("help", {}),
    "unlink": ("unlink_confirm", {"command": "unlink"}),
}


def chat_hash(chat_id: int) -> str:
    return hashlib.sha256(str(chat_id).encode()).hexdigest()[:12]


def parse_command(text: str, bot_username: str) -> tuple[str, str] | None:
    """`/week@dataxland_bot arg` → (`week`, `arg`). Lệnh gửi cho bot khác trả None."""
    if not text.startswith("/"):
        return None
    head, _, arg = text.strip().partition(" ")
    cmd, _, target = head[1:].partition("@")
    if target and target.lower() != bot_username.lower():
        return None
    return cmd.lower(), arg.strip()


class Handler:
    def __init__(self, tg: TelegramApi, api: BotApiClient, bot_username: str) -> None:
        self.tg, self.api, self.bot_username = tg, api, bot_username

    async def reply(self, chat_id: int, res: ApiResult) -> None:
        msg = res.message
        if msg is None and res.status == 403:
            res = await self.api.message("not_linked", chat_id)
            msg = res.message
        if msg is None:
            log.warning("API không trả tin", extra={"status": res.status, "chat": chat_hash(chat_id)})
            return
        try:
            await self.tg.send(chat_id, msg["text_html"], msg.get("buttons"))
        except BotApiError as exc:
            if exc.code == 403:  # người dùng chặn bot hoặc bot bị xóa khỏi nhóm
                await self.api.chat_left(chat_id, "bot_blocked" if chat_id > 0 else "bot_removed")
            else:
                raise

    async def handle(self, update: dict[str, Any]) -> None:
        if "callback_query" in update:
            await self.on_callback(update["callback_query"])
        elif "my_chat_member" in update:
            await self.on_member(update["my_chat_member"])
        elif "message" in update:
            await self.on_message(update["message"])

    async def on_message(self, m: dict[str, Any]) -> None:
        chat = m.get("chat") or {}
        chat_id = int(chat["id"])
        text = str(m.get("text") or "")
        parsed = parse_command(text, self.bot_username)
        log.info(
            "tin nhắn",
            extra={"chat": chat_hash(chat_id), "command": parsed[0] if parsed else None, "chat_type": chat.get("type")},
        )
        if parsed is None:
            if chat.get("type") == "private" and text:
                await self.reply(chat_id, await self.api.message("help", chat_id, free_text=True))
            return
        cmd, arg = parsed
        if cmd == "start":
            if arg:
                user = (m.get("from") or {}).get("id")
                await self.reply(chat_id, await self.api.link(arg, chat, user))
            else:
                await self.reply(chat_id, await self.api.message("help", chat_id))
            return
        if cmd not in COMMANDS:
            return
        kind, body = COMMANDS[cmd]
        await self.reply(chat_id, await self.api.message(kind, chat_id, **body))

    async def on_callback(self, q: dict[str, Any]) -> None:
        data = str(q.get("data") or "")
        chat_id = int(((q.get("message") or {}).get("chat") or {})["id"])
        await self.tg.answer_callback(str(q.get("id")))
        if data.startswith("kt:"):
            _, cmd, tenant_id = [*data.split(":", 2), "", ""][:3]
            if cmd in COMMANDS:
                kind, body = COMMANDS[cmd]
                if kind == "unlink_confirm":
                    await self.reply(chat_id, await self.api.unlink(chat_id, tenant_id))
                else:
                    await self.reply(chat_id, await self.api.message(kind, chat_id, tenant_id=tenant_id, **body))
        elif data.startswith("ku:"):
            target = data[3:]
            await self.reply(chat_id, await self.api.unlink(chat_id, None if target == "*" else target))

    async def on_member(self, u: dict[str, Any]) -> None:
        status = ((u.get("new_chat_member") or {}).get("status")) or ""
        chat = u.get("chat") or {}
        if status in ("kicked", "left"):
            reason = "bot_blocked" if chat.get("type") == "private" else "bot_removed"
            await self.api.chat_left(int(chat["id"]), reason)
