"""Gọi services/api thay chat (spec 05 §3.4, spec 08 §2): token nội bộ, `X-Service: bot`, `X-Telegram-Chat-Id`."""

from __future__ import annotations

from typing import Any

import httpx

from dx_common.config import get_settings


class ApiResult:
    def __init__(self, status: int, body: dict[str, Any]) -> None:
        self.status, self.body = status, body

    @property
    def message(self) -> dict[str, Any] | None:
        """Tin đã dựng sẵn: thân phản hồi (200) hoặc `message` kèm lỗi (429)."""
        if "text_html" in self.body:
            return self.body
        m = self.body.get("message")
        return m if isinstance(m, dict) else None


class BotApiClient:
    def __init__(
        self, base: str | None = None, token: str | None = None, client: httpx.AsyncClient | None = None
    ) -> None:
        s = get_settings()
        self.base = (base or s.api_internal_url).rstrip("/")
        self.token = token or s.internal_api_token
        self.client = client or httpx.AsyncClient(timeout=60)

    def _headers(self, chat_id: int | None) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self.token}", "X-Service": "bot"}
        if chat_id is not None:
            h["X-Telegram-Chat-Id"] = str(chat_id)
        return h

    async def post(self, path: str, body: dict[str, Any], chat_id: int | None) -> ApiResult:
        r = await self.client.post(f"{self.base}{path}", json=body, headers=self._headers(chat_id))
        return ApiResult(r.status_code, r.json() if r.content else {})

    async def link(self, code: str, chat: dict[str, Any], user_id: int | None) -> ApiResult:
        chat_type = chat.get("type", "private")
        return await self.post(
            "/v1/telegram/links",
            {
                "code": code,
                "chat_id": chat["id"],
                "chat_type": "supergroup" if chat_type == "channel" else chat_type,
                "chat_title": chat.get("title"),
                "telegram_user_id": user_id,
            },
            chat["id"],
        )

    async def message(self, kind: str, chat_id: int, **body: Any) -> ApiResult:
        return await self.post(f"/v1/telegram/messages/{kind}", body, chat_id)

    async def unlink(self, chat_id: int, tenant_id: str | None) -> ApiResult:
        return await self.post("/v1/telegram/unlink", {"tenant_id": tenant_id}, chat_id)

    async def chat_left(self, chat_id: int, reason: str) -> ApiResult:
        return await self.post("/v1/telegram/chat-left", {"chat_id": chat_id, "reason": reason}, None)
