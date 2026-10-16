"""Làm mới pre-aggregation của Cube cho một khách (spec 03 §10.2, spec 04 §3.2 bước `refresh_cube`)."""

from __future__ import annotations

import time
from typing import Any, Protocol

import httpx
import jwt

from dx_common.config import get_settings


class CubeLike(Protocol):
    def refresh(self, tenant_id: str, dataset_prefix: str) -> dict[str, Any]: ...


def cube_token(tenant_id: str, dataset_prefix: str, ttl: int = 600) -> str:
    now = int(time.time())
    return jwt.encode(
        {"tenant_id": tenant_id, "dataset_prefix": dataset_prefix, "iat": now, "exp": now + ttl},
        get_settings().cube_api_secret,
        algorithm="HS256",
    )


class CubeAdmin:
    def __init__(self, base_url: str | None = None, timeout_s: int = 900) -> None:
        self.base = (base_url or get_settings().cube_api_url).rstrip("/")
        self.timeout_s = timeout_s

    def _post(self, token: str, body: dict[str, Any]) -> Any:
        with httpx.Client(timeout=60) as c:
            r = c.post(f"{self.base}/cubejs-api/v1/pre-aggregations/jobs", json=body, headers={"Authorization": token})
        if r.status_code >= 400:
            raise RuntimeError(f"Cube {r.status_code}: {r.text[:300]}")
        return r.json()

    def refresh(self, tenant_id: str, dataset_prefix: str) -> dict[str, Any]:
        token = cube_token(tenant_id, dataset_prefix)
        ctx = {"securityContext": {"tenant_id": tenant_id, "dataset_prefix": dataset_prefix}}
        tokens = self._post(
            token, {"action": "post", "selector": {"contexts": [ctx], "timezones": ["Asia/Ho_Chi_Minh"]}}
        )
        if not tokens:
            return {"jobs": 0}
        deadline = time.time() + self.timeout_s
        while time.time() < deadline:
            jobs = self._post(token, {"action": "get", "tokens": tokens})
            statuses = [str(j.get("status")) for j in jobs]
            if all(s == "done" for s in statuses):
                return {"jobs": len(tokens)}
            if any(s.startswith("failure") for s in statuses):
                raise RuntimeError(f"pre-aggregation lỗi: {statuses}")
            time.sleep(2)
        raise TimeoutError("pre-aggregation quá thời gian")
