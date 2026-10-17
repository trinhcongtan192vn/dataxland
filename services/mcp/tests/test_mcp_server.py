"""MCP server chỉ đọc (spec 09 §2, §9)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import respx

API = "http://api.test"


def test_fr_ai_01_mcp_has_three_readonly_tools() -> None:
    from mcp import Client

    from dx_mcp.server import build_server

    async def run() -> list[Any]:
        async with Client(build_server()) as c:
            return list((await c.list_tools()).tools)

    tools = asyncio.run(run())
    assert sorted(t.name for t in tools) == ["describe_metric", "list_metrics", "query_metric"]
    for t in tools:
        assert t.annotations.read_only_hint is True and t.annotations.destructive_hint is False
        assert "tenant_id" not in json.dumps(t.input_schema)


def test_fr_ai_01_tenant_not_from_model() -> None:
    from dx_mcp import tools

    seen: list[tuple[dict[str, Any], dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((json.loads(request.content), dict(request.headers)))
        rows = [{"net_revenue": i} for i in range(250)]
        return httpx.Response(
            200,
            json={
                "tenant_id": "demo_seller",
                "time": {"from": "2026-10-05", "to": "2026-10-11"},
                "metrics": {"net_revenue": {"name_vi": "Doanh thu thực nhận", "version": "1.0.0", "unit": "VND"}},
                "rows": rows,
                "data_as_of": None,
                "warnings": [],
            },
        )

    async def run() -> dict[str, Any]:
        async with httpx.AsyncClient() as http:
            api = tools.ApiClient(API, "tok", http)
            return await tools.query_metric(
                api, "SESSION", {"metrics": ["net_revenue"], "tenant_id": "demo_agency", "dataset": "t_demo_agency"}
            )

    with respx.mock() as m:
        m.post(f"{API}/v1/metrics/query").mock(side_effect=handler)
        out = asyncio.run(run())
    body, headers = seen[0]
    assert body == {"metrics": ["net_revenue"], "dimensions": []}  # tham số lạ của model bị bỏ
    assert headers["x-dx-session"] == "SESSION" and headers["x-service"] == "mcp"
    assert headers["authorization"] == "Bearer tok" and "x-tenant-id" not in headers
    assert len(out["rows"]) == 200 and "truncated" in out


def test_tool_without_session_fails() -> None:
    from mcp import Client

    from dx_mcp.server import build_server

    async def run() -> Any:
        async with Client(build_server()) as c:
            return await c.call_tool("list_metrics", {})

    res = asyncio.run(run())
    assert res.is_error
