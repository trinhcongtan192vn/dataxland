"""Ba công cụ chỉ đọc (spec 09 §2): gọi lại API bằng token nội bộ của dịch vụ `mcp` kèm token phiên do API ký.

Khách và quyền nằm trong token phiên, không trong tham số của model: tham số lạ như `tenant_id` bị bỏ.
"""

from __future__ import annotations

from typing import Any

import httpx

from dx_common.ai_tools import SESSION_HEADER, clean_query_args, shape_result
from dx_common.config import get_settings


class ToolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ApiClient:
    def __init__(self, base: str | None = None, token: str | None = None, client: httpx.AsyncClient | None = None):
        s = get_settings()
        self.base = (base or s.api_internal_url).rstrip("/")
        self.token = token or s.internal_api_token
        self.client = client or httpx.AsyncClient(timeout=30)

    def _headers(self, session: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "X-Service": "mcp", SESSION_HEADER: session}

    async def _send(self, method: str, path: str, session: str, body: dict[str, Any] | None = None) -> Any:
        if not session:
            raise ToolError("MCP_SESSION_REQUIRED", "Thiếu token phiên")
        r = await self.client.request(method, f"{self.base}{path}", json=body, headers=self._headers(session))
        data = r.json() if r.content else {}
        if r.status_code >= 400:
            err = data.get("error", {}) if isinstance(data, dict) else {}
            raise ToolError(str(err.get("code", r.status_code)), str(err.get("message", "Lỗi gọi API")))
        return data


def _brief(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "metric": m["metric"],
        "name_vi": m["name_vi"],
        "unit": m["unit"],
        "version": m["version"],
        "dimensions": [d["name"] for d in m.get("dimensions", [])],
        "synonyms_vi": m.get("synonyms_vi", []),
    }


async def list_metrics(api: ApiClient, session: str) -> dict[str, Any]:
    items = await api._send("GET", "/v1/metrics", session)
    return {"metrics": [_brief(m) for m in items]}


async def describe_metric(api: ApiClient, session: str, name: str) -> dict[str, Any]:
    items = await api._send("GET", "/v1/metrics", session)
    for m in items:
        if m["metric"] == name:
            keep = ("metric", "name_vi", "description_vi", "version", "unit", "good_direction", "formula_vi")
            return {
                **{k: m.get(k) for k in keep},
                "dimensions": m.get("dimensions", []),
                "time_grains": m.get("time_grains", []),
            }
    raise ToolError("METRIC_UNKNOWN", f"Không có chỉ số {name} hoặc bạn không được xem")


async def query_metric(api: ApiClient, session: str, args: dict[str, Any]) -> dict[str, Any]:
    res = await api._send("POST", "/v1/metrics/query", session, clean_query_args(args))
    return shape_result(res)
