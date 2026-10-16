"""Gọi Cube REST `/cubejs-api/v1/load` với JWT ký bằng `CUBE_API_SECRET`, payload `{tenant_id, dataset_prefix}`
(spec 03 §4). Chỉ `services/api` gọi Cube."""

from __future__ import annotations

import time
from typing import Any, Protocol

import httpx
import jwt

from app.errors import ApiError
from dx_common.config import get_settings
from dx_common.logging import get_logger

log = get_logger(__name__)


class CubeLike(Protocol):
    def load(self, tenant_id: str, dataset_prefix: str, query: dict[str, Any]) -> list[dict[str, Any]]: ...


def cube_token(tenant_id: str, dataset_prefix: str, ttl: int = 300) -> str:
    now = int(time.time())
    return jwt.encode(
        {"tenant_id": tenant_id, "dataset_prefix": dataset_prefix, "iat": now, "exp": now + ttl},
        get_settings().cube_api_secret,
        algorithm="HS256",
    )


class CubeClient:
    def __init__(self, base_url: str | None = None, timeout_s: float = 30.0) -> None:
        self.base = (base_url or get_settings().cube_api_url).rstrip("/")
        self.timeout_s = timeout_s

    def load(self, tenant_id: str, dataset_prefix: str, query: dict[str, Any]) -> list[dict[str, Any]]:
        headers = {"Authorization": cube_token(tenant_id, dataset_prefix)}
        deadline = time.monotonic() + self.timeout_s
        try:
            with httpx.Client(timeout=self.timeout_s) as c:
                while True:
                    r = c.post(f"{self.base}/cubejs-api/v1/load", json={"query": query}, headers=headers)
                    if r.status_code == 200:
                        body = r.json()
                        if body.get("error") == "Continue wait":
                            if time.monotonic() > deadline:
                                break
                            time.sleep(0.3)
                            continue
                        return list(body.get("data") or [])
                    if r.status_code in (401, 403):
                        raise ApiError(403, "TENANT_FORBIDDEN", "Cube từ chối truy vấn của khách này")
                    log.warning("Cube trả %s: %s", r.status_code, r.text[:300])
                    break
        except httpx.HTTPError as exc:
            log.warning("không gọi được Cube: %s", type(exc).__name__)
        raise ApiError(503, "CUBE_UNAVAILABLE", "Dịch vụ chỉ số tạm thời không sẵn sàng, thử lại sau ít phút")


_client: CubeLike | None = None


def get_cube() -> CubeLike:
    global _client
    if _client is None:
        _client = CubeClient()
    return _client


def set_cube(client: CubeLike | None) -> None:
    global _client
    _client = client
