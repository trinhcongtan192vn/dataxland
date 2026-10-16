"""Gọi `services/api` từ Dagster bằng token nội bộ (spec 05 §3.3, §6.10)."""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from dx_common.config import get_settings


class Api(Protocol):
    def tenants(self, status: list[str] | None = None) -> list[dict[str, Any]]: ...
    def record_run(self, body: dict[str, Any]) -> None: ...
    def publish(self, type: str, tenant_id: str | None, payload: dict[str, Any], producer: str) -> str: ...
    def run_anomalies(self, tenant_id: str, run_id: str) -> dict[str, Any]: ...
    def build_report(
        self, tenant_id: str, period: str | None, run_id: str | None, data_stale: bool
    ) -> dict[str, Any]: ...
    def build_health_check(self, check_id: str) -> dict[str, Any]: ...
    def post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]: ...


class ApiClient:
    def __init__(self, base_url: str | None = None, token: str | None = None, service: str = "dagster") -> None:
        s = get_settings()
        self.base = (base_url or s.api_internal_url).rstrip("/")
        self.headers = {"Authorization": f"Bearer {token or s.internal_api_token}", "X-Service": service}

    def _req(self, method: str, path: str, **kw: Any) -> Any:
        with httpx.Client(timeout=60) as c:
            r = c.request(method, self.base + path, headers=self.headers, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"API {method} {path} → {r.status_code}: {r.text[:300]}")
        return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else None

    def tenants(self, status: list[str] | None = None) -> list[dict[str, Any]]:
        return list(self._req("GET", "/v1/internal/tenants", params=[("status", s) for s in (status or [])]))

    def record_run(self, body: dict[str, Any]) -> None:
        self._req("POST", "/v1/internal/runs", json=body)

    def publish(self, type: str, tenant_id: str | None, payload: dict[str, Any], producer: str) -> str:
        return str(
            self._req(
                "POST",
                "/v1/events",
                json={"type": type, "tenant_id": tenant_id, "payload": payload, "producer": producer},
            )["event_id"]
        )

    def run_anomalies(self, tenant_id: str, run_id: str) -> dict[str, Any]:
        return dict(self._req("POST", "/v1/internal/anomalies/run", json={"tenant_id": tenant_id, "run_id": run_id}))

    def build_report(self, tenant_id: str, period: str | None, run_id: str | None, data_stale: bool) -> dict[str, Any]:
        return dict(
            self._req(
                "POST",
                "/v1/internal/reports/build",
                json={"tenant_id": tenant_id, "period": period, "run_id": run_id, "data_stale": data_stale},
            )
        )

    def build_health_check(self, check_id: str) -> dict[str, Any]:
        return dict(self._req("POST", f"/v1/internal/health-checks/{check_id}/build"))

    def post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        return dict(self._req("POST", path, json=body or {}) or {})
