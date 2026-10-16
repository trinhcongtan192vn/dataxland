"""Kênh Telegram: Bot API `sendMessage` với `parse_mode=HTML` và inline keyboard (spec 04 §5.1, spec 08)."""

from __future__ import annotations

from typing import Any

import httpx

from app.notify.types import DeliveryResult, Recipient, RenderedMessage
from dx_common.config import get_settings

MAX_LEN = 4096


def keyboard(message: RenderedMessage) -> dict[str, Any] | None:
    rows = []
    for b in message.buttons:
        if b.url:
            rows.append([{"text": b.label, "url": b.url}])
        elif b.callback_data:
            rows.append([{"text": b.label, "callback_data": b.callback_data}])
    return {"inline_keyboard": rows} if rows else None


class TelegramChannel:
    name = "telegram"

    def supports(self, recipient: Recipient) -> bool:
        return recipient.kind in ("telegram_chat", "team") and recipient.address.lstrip("-").isdigit()

    async def send(self, recipient: Recipient, message: RenderedMessage) -> DeliveryResult:
        s = get_settings()
        if not s.telegram_bot_token:
            return DeliveryResult(ok=False, error_code="TELEGRAM_NOT_CONFIGURED", connection_error=True)
        text = (message.telegram_html or message.text)[:MAX_LEN]
        payload: dict[str, Any] = {
            "chat_id": int(recipient.address),
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        kb = keyboard(message)
        if kb:
            payload["reply_markup"] = kb
        url = f"{s.telegram_api_base}/bot{s.telegram_bot_token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, json=payload)
        except httpx.HTTPError:
            return DeliveryResult(ok=False, error_code="TELEGRAM_CONNECTION", connection_error=True)
        if resp.status_code == 200 and resp.json().get("ok"):
            return DeliveryResult(ok=True)
        if resp.status_code == 403:
            # Người dùng chặn bot hoặc bot bị xóa khỏi nhóm.
            return DeliveryResult(ok=False, error_code="TELEGRAM_FORBIDDEN", retryable=False)
        if resp.status_code == 400:
            return DeliveryResult(ok=False, error_code="TELEGRAM_BAD_REQUEST", retryable=False)
        if resp.status_code == 429:
            return DeliveryResult(ok=False, error_code="TELEGRAM_RATE_LIMITED")
        return DeliveryResult(
            ok=False, error_code=f"TELEGRAM_HTTP_{resp.status_code}", connection_error=resp.status_code >= 500
        )
