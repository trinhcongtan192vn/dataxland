"""Dịch vụ Telegram bot (spec 08 §1).

- Webhook `POST /tg/webhook`: kiểm header `X-Telegram-Bot-Api-Secret-Token`; sai → 401.
- Khởi động ở chế độ webhook: `setWebhook` (secret, allowed_updates) và `setMyCommands`.
- `local`: `BOT_MODE=polling` dùng long polling.
- `GET /healthz`: gọi `getMe`.
"""

from __future__ import annotations

import asyncio
import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

from bot.api_client import BotApiClient
from bot.handlers import Handler
from bot.telegram_api import TelegramApi
from dx_common.config import get_settings
from dx_common.logging import configure_logging, get_logger

log = get_logger(__name__)


def create_app(tg: TelegramApi | None = None, api: BotApiClient | None = None, setup: bool = True) -> FastAPI:
    s = get_settings()
    tg = tg or TelegramApi()
    api = api or BotApiClient()
    handler = Handler(tg, api, s.telegram_bot_username)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if setup and s.bot_mode == "webhook" and s.bot_public_url:
            await tg.setup_webhook(f"{s.bot_public_url.rstrip('/')}/tg/webhook", s.telegram_webhook_secret)
            log.info("đã đăng ký webhook")
        yield

    app = FastAPI(title="DataxLand Telegram bot", lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.post("/tg/webhook")
    async def webhook(
        request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)
    ) -> JSONResponse:
        secret = get_settings().telegram_webhook_secret
        if (
            not secret
            or not x_telegram_bot_api_secret_token
            or not hmac.compare_digest(x_telegram_bot_api_secret_token, secret)
        ):
            return JSONResponse({"ok": False}, status_code=401)
        update: dict[str, Any] = await request.json()
        try:
            await handler.handle(update)
        except Exception as exc:  # không để Telegram gửi lại vô hạn; lỗi đã log
            log.error("xử lý cập nhật lỗi", extra={"error": type(exc).__name__})
        return JSONResponse({"ok": True})

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        try:
            me = await tg.get_me()
        except Exception as exc:
            return JSONResponse({"status": "error", "error": type(exc).__name__}, status_code=503)
        return JSONResponse({"status": "ok", "username": me.get("username")})

    app.state.handler = handler
    return app


async def poll(handler: Handler, tg: TelegramApi) -> None:  # pragma: no cover - vòng lặp chạy thật
    offset: int | None = None
    await tg.call("deleteWebhook", {"drop_pending_updates": False})
    while True:
        try:
            updates = await tg.get_updates(offset)
        except Exception as exc:
            log.warning("getUpdates lỗi", extra={"error": type(exc).__name__})
            await asyncio.sleep(5)
            continue
        for u in updates:
            offset = int(u["update_id"]) + 1
            try:
                await handler.handle(u)
            except Exception as exc:
                log.error("xử lý cập nhật lỗi", extra={"error": type(exc).__name__})


def main() -> None:  # pragma: no cover
    import uvicorn

    configure_logging()
    s = get_settings()
    if s.bot_mode == "polling":
        tg = TelegramApi()
        handler = Handler(tg, BotApiClient(), s.telegram_bot_username)
        asyncio.run(poll(handler, tg))
    else:
        uvicorn.run(create_app(), host="0.0.0.0", port=8100)  # noqa: S104 - chạy trong container, Caddy đứng trước


if __name__ == "__main__":  # pragma: no cover
    main()
