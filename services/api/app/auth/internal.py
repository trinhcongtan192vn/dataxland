"""Xác thực dịch vụ nội bộ (spec 05 §3.3): `Authorization: Bearer <INTERNAL_API_TOKEN>` kèm `X-Service`."""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from fastapi import Header

from app.errors import ApiError
from dx_common.config import get_settings

SERVICES = frozenset({"dagster", "bot", "ops", "cube", "mcp", "worker"})


@dataclass(frozen=True)
class ServiceCaller:
    service: str


def bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def is_internal_token(token: str | None) -> bool:
    expected = get_settings().internal_api_token
    return bool(token and expected and hmac.compare_digest(token, expected))


def require_service(
    authorization: str | None = Header(default=None),
    x_service: str | None = Header(default=None),
) -> ServiceCaller:
    """Dependency cho `/v1/internal/*`. Token người dùng → 403 (test_internal_endpoints_reject_user_token)."""
    token = bearer(authorization)
    if not token:
        raise ApiError(401, "UNAUTHENTICATED", "Thiếu token")
    if not is_internal_token(token):
        raise ApiError(403, "INTERNAL_ONLY", "Endpoint chỉ dành cho dịch vụ nội bộ")
    if x_service not in SERVICES:
        raise ApiError(403, "INTERNAL_ONLY", "X-Service không hợp lệ")
    return ServiceCaller(service=x_service)
