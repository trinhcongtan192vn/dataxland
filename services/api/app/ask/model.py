"""Gọi model và chạy công cụ cho bộ máy hỏi đáp và agent (spec 09 §3, §8).

- `ModelCaller`: (system, messages, tools) → phản hồi đã chuẩn hóa {content, stop_reason, usage}. Test dùng model giả.
- `ToolRunner`: chạy ba công cụ chỉ đọc. `McpToolRunner` gọi MCP server bằng token phiên; `LocalToolRunner` gọi thẳng
  bộ máy chỉ số trong tiến trình (khi không cấu hình `MCP_URL`, ví dụ khi test). Cả hai cùng định nghĩa công cụ
  (`dx_common.ai_tools`) và cùng kết quả.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.auth.context import AuthContext, sign_mcp_session
from app.errors import ApiError
from app.metrics.engine import QueryIn, check_metric, query, visible_metrics
from dx_common.ai_tools import SESSION_HEADER, TOOL_NAMES, clean_query_args, shape_result
from dx_common.config import get_settings
from dx_common.logging import get_logger

log = get_logger("api.ask")

ModelCaller = Callable[[str, list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any]]

# Giá USD mỗi triệu token (vào, ra) theo họ model; dùng để ghi chi phí (spec 09 §6, NFR-08).
PRICES = {"haiku": (1.0, 5.0), "sonnet": (3.0, 15.0), "opus": (5.0, 25.0), "fable": (5.0, 25.0)}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    pin, pout = next((v for k, v in PRICES.items() if k in model), PRICES["sonnet"])
    return (Decimal(input_tokens) * Decimal(str(pin)) + Decimal(output_tokens) * Decimal(str(pout))) / Decimal(
        1_000_000
    )


def anthropic_caller(model: str, timeout: float = 30.0, max_tokens: int = 1500) -> ModelCaller:  # pragma: no cover
    import anthropic

    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key, timeout=timeout, max_retries=1)

    def call(system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        res = client.messages.create(  # type: ignore[call-overload]
            model=model, max_tokens=max_tokens, temperature=0, system=system, messages=messages, tools=tools
        )
        blocks: list[dict[str, Any]] = []
        for b in res.content:
            if b.type == "text":
                blocks.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": dict(b.input or {})})
        return {
            "content": blocks,
            "stop_reason": res.stop_reason,
            "usage": {"input_tokens": res.usage.input_tokens, "output_tokens": res.usage.output_tokens},
        }

    return call


def default_caller(kind: str = "ask") -> ModelCaller | None:
    s = get_settings()
    if not s.anthropic_api_key:
        return None
    return anthropic_caller(s.anthropic_model_ask if kind == "ask" else s.anthropic_model_agent)


class ToolRunner(Protocol):
    def run(self, name: str, args: dict[str, Any]) -> dict[str, Any]: ...


def _jsonable(obj: Any) -> Any:
    return json.loads(json.dumps(obj, default=str))


class LocalToolRunner:
    """Chạy công cụ ngay trong API với đúng `AuthContext` của người hỏi (quyền như mọi request)."""

    def __init__(self, ctx: AuthContext, db: Session) -> None:
        self.ctx, self.db = ctx, db

    def run(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name not in TOOL_NAMES:
            raise ApiError(400, "TOOL_UNKNOWN", f"Không có công cụ {name}")
        if name == "list_metrics":
            return {
                "metrics": [
                    {
                        "metric": m.metric,
                        "name_vi": m.name_vi,
                        "unit": m.unit,
                        "version": m.version,
                        "dimensions": list(m.dimensions),
                        "synonyms_vi": list(m.synonyms_vi),
                    }
                    for m in sorted(visible_metrics(self.ctx), key=lambda x: x.metric)
                ]
            }
        if name == "describe_metric":
            m = check_metric(self.ctx, str(args.get("name", "")))
            hb = m.handbook or {}
            return {
                "metric": m.metric,
                "name_vi": m.name_vi,
                "description_vi": m.description_vi,
                "version": m.version,
                "unit": m.unit,
                "good_direction": m.good_direction,
                "formula_vi": hb.get("formula_vi"),
                "dimensions": list(m.dimensions),
                "time_grains": list(m.time_grains),
            }
        body = QueryIn.model_validate(clean_query_args(args))
        return dict(_jsonable(shape_result(query(self.ctx, body, db=self.db, caller=self.ctx.caller))))


class McpToolRunner:
    """Gọi MCP server (streamable HTTP) với token phiên 5 phút trong header; khách nằm trong token."""

    def __init__(self, ctx: AuthContext, url: str, fallback: ToolRunner | None = None) -> None:
        self.url = url
        self.session = sign_mcp_session(ctx)
        self.fallback = fallback

    async def _call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        import httpx2
        from mcp import Client
        from mcp.client.streamable_http import streamable_http_client

        async with (
            httpx2.AsyncClient(headers={SESSION_HEADER: self.session}, timeout=30) as http,
            Client(streamable_http_client(self.url, http_client=http)) as client,
        ):
            res = await client.call_tool(name, args)
        if res.is_error:
            text = "".join(getattr(c, "text", "") for c in res.content)
            raise ApiError(400, "TOOL_ERROR", text or "Công cụ lỗi")
        if res.structured_content is not None:
            return dict(res.structured_content)
        return dict(json.loads("".join(getattr(c, "text", "") for c in res.content) or "{}"))

    def run(self, name: str, args: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover - cần MCP server
        try:
            return asyncio.run(self._call(name, args))
        except ApiError:
            raise
        except Exception:
            # Local: stack chưa bật profile `ai` thì chạy công cụ trong tiến trình (ADR 0002).
            if self.fallback is None:
                raise
            log.warning("MCP server không phản hồi, chạy công cụ trong API", extra={"tool": name})
            return self.fallback.run(name, args)


def default_runner(ctx: AuthContext, db: Session) -> ToolRunner:
    s = get_settings()
    if not s.mcp_url:
        return LocalToolRunner(ctx, db)
    return McpToolRunner(ctx, s.mcp_url, fallback=LocalToolRunner(ctx, db) if s.dx_env == "local" else None)
