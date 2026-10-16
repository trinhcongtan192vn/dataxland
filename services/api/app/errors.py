"""Lỗi theo RFC 9457 `application/problem+json` với `type`, `title`, `detail`, `code` (spec 00 §3.4)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from dx_common.logging import get_logger, request_id_var

log = get_logger(__name__)

PROBLEM = "application/problem+json"

_TITLES = {
    400: "Yêu cầu không hợp lệ",
    401: "Chưa xác thực",
    403: "Không có quyền",
    404: "Không tìm thấy",
    409: "Xung đột",
    413: "Dữ liệu quá lớn",
    422: "Dữ liệu không hợp lệ",
    429: "Quá nhiều yêu cầu",
    500: "Lỗi hệ thống",
    503: "Dịch vụ tạm thời không sẵn sàng",
}


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        detail: str | None = None,
        *,
        title: str | None = None,
        headers: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.detail = detail
        self.title = title or _TITLES.get(status, "Lỗi")
        self.headers = headers or {}
        self.extra = extra or {}


def problem(status: int, code: str, detail: str | None, title: str | None = None, **extra: Any) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://docs.dataxland.vn/errors/{code.lower()}",
        "title": title or _TITLES.get(status, "Lỗi"),
        "status": status,
        "detail": detail,
        "code": code,
    }
    rid = request_id_var.get()
    if rid:
        body["request_id"] = rid
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        resp = problem(exc.status, exc.code, exc.detail, exc.title, **exc.extra)
        for k, v in exc.headers.items():
            resp.headers[k] = v
        return resp

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": [str(x) for x in e.get("loc", [])], "msg": str(e.get("msg", "")), "type": str(e.get("type", ""))}
            for e in exc.errors()
        ]
        return problem(422, "VALIDATION_ERROR", "Dữ liệu gửi lên không hợp lệ", errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 401: "UNAUTHENTICATED"}.get(exc.status_code, "HTTP_ERROR")
        return problem(exc.status_code, code, str(exc.detail) if exc.detail else None)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("lỗi chưa xử lý: %s", type(exc).__name__)
        return problem(500, "INTERNAL_ERROR", "Đã có lỗi xảy ra. Đội ngũ đã được ghi nhận.")
