"""MCP server chỉ đọc chỉ số (spec 09 §2): ba công cụ, transport streamable HTTP, chỉ mạng nội bộ.

Token phiên đến trong header `X-Dx-Session` của request MCP; server chuyển nó khi gọi lại API.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp_types import ToolAnnotations

from dx_common.ai_tools import SESSION_HEADER, TOOLS
from dx_mcp import tools

READONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
_DESC = {t["name"]: str(t["description"]) for t in TOOLS}


def _session(ctx: Context[Any, Any]) -> str:
    headers = ctx.headers or {}
    for k, v in headers.items():
        if k.lower() == SESSION_HEADER.lower():
            return str(v)
    return ""


def build_server(api: tools.ApiClient | None = None) -> MCPServer[Any]:
    server: MCPServer[Any] = MCPServer(
        name="dataxland-metrics", instructions="Chỉ đọc số từ thư viện chỉ số DataxLand."
    )
    client = api or tools.ApiClient()

    @server.tool(description=_DESC["list_metrics"], annotations=READONLY)
    async def list_metrics(ctx: Context[Any, Any]) -> dict[str, Any]:
        return await tools.list_metrics(client, _session(ctx))

    @server.tool(description=_DESC["describe_metric"], annotations=READONLY)
    async def describe_metric(name: str, ctx: Context[Any, Any]) -> dict[str, Any]:
        return await tools.describe_metric(client, _session(ctx), name)

    @server.tool(description=_DESC["query_metric"], annotations=READONLY)
    async def query_metric(
        metrics: list[str],
        ctx: Context[Any, Any],
        dimensions: list[str] | None = None,
        time: dict[str, str] | None = None,
        grain: str | None = None,
        filters: list[dict[str, Any]] | None = None,
        compare: str | None = None,
    ) -> dict[str, Any]:
        args = {
            "metrics": metrics,
            "dimensions": dimensions,
            "time": time,
            "grain": grain,
            "filters": filters,
            "compare": compare,
        }
        return await tools.query_metric(client, _session(ctx), args)

    return server


def main() -> None:  # pragma: no cover - chạy dịch vụ
    import uvicorn

    from dx_common.logging import configure_logging

    configure_logging()
    app = build_server().streamable_http_app()
    uvicorn.run(app, host="0.0.0.0", port=8200)  # noqa: S104 - chỉ mạng nội bộ


if __name__ == "__main__":  # pragma: no cover
    main()
