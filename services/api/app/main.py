"""Tạo app FastAPI, middleware request id, lỗi RFC 9457 (spec 05 §1, spec 00 §3.4)."""

from __future__ import annotations

import re
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.errors import install_error_handlers
from app.routers import register_routers
from dx_common.config import get_settings
from dx_common.ids import new_ulid
from dx_common.logging import configure_logging, get_logger, request_id_var, tenant_id_var

log = get_logger("api.access")
_RID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def create_app() -> FastAPI:
    configure_logging()
    s = get_settings()
    app = FastAPI(
        title="DataxLand API",
        version="1.0.0",
        description="API của DataxLand: chỉ số, báo cáo, nhập liệu, quyết định, Telegram, vận hành.",
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url=None,
    )
    install_error_handlers(app)
    origins = sorted({s.dx_public_base_url.rstrip("/"), "http://localhost:3000", "http://127.0.0.1:3000"})
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id", "Retry-After", "Content-Disposition"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = request.headers.get("x-request-id")
        if not rid or not _RID_RE.match(rid):
            rid = new_ulid()
        token_rid = request_id_var.set(rid)
        token_tenant = tenant_id_var.set(None)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token_rid)
        response.headers["X-Request-Id"] = rid
        # Không log query string hay body: có thể chứa token (spec 00 §3.4).
        request_id_var.set(rid)
        log.info(
            "request",
            extra={
                "dx": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": round((time.perf_counter() - start) * 1000),
                }
            },
        )
        request_id_var.set(None)
        tenant_id_var.reset(token_tenant)
        return response

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    register_routers(app)
    return app


app = create_app()
