"""Bộ máy hỏi đáp dùng chung cho cổng và Telegram (spec 09 §3, FR-AI-01, FR-AI-02, FR-TG-06).

`ask(db, ctx, question, channel)`: kiểm tra trước → bộ nhớ đệm → dựng ngữ cảnh → model với ba công cụ chỉ đọc và
`final_answer` → kiểm tra sau → chân trang từ nhật ký công cụ → ghi `ask_logs`, `metric_requests`, chi phí.
Giới hạn tần suất do router áp trước khi gọi hàm này.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ask import guard
from app.ask.model import ModelCaller, ToolRunner, cost_usd, default_caller, default_runner
from app.ask.prompt import build_system
from app.auth.context import AuthContext
from app.db.models import AskLog, FxManualRate, MetricRequest, TenantCost
from app.errors import ApiError
from app.metrics.engine import data_status
from app.metrics.registry import get_registry
from dx_common.ai_tools import TOOLS
from dx_common.config import get_settings
from dx_common.ids import new_ulid
from dx_common.logging import get_logger
from dx_common.timeutil import iso_z, month_start, now_utc, today_vn

log = get_logger("api.ask")

Channel = Literal["portal", "telegram", "eval"]
MAX_TOOL_CALLS = 6
TIME_BUDGET_SECONDS = 30
HISTORY_TURNS = 6
CACHE_DAYS = 7
USD_VND_FALLBACK = Decimal(26_000)

MISSING_ANSWER = "Hiện chưa có chỉ số cho câu hỏi này. Đội ngũ đã ghi nhận."
FAILED_ANSWER = "Chưa trả lời được câu hỏi này. Bạn thử hỏi cụ thể hơn: chỉ số nào, khoảng thời gian nào."
NO_MODEL_ANSWER = "Tính năng hỏi đáp chưa được bật cho môi trường này. Bạn dùng dashboard hoặc /week, /month, /report."

FINAL_TOOL: dict[str, Any] = {
    "name": "final_answer",
    "description": "Gửi câu trả lời cuối cùng. Gọi đúng một lần khi đã có đủ số.",
    "input_schema": {
        "type": "object",
        "properties": {
            "answer_vi": {"type": "string", "description": "Câu trả lời tiếng Việt, không kèm chân trang"},
            "metrics_cited": {"type": "array", "items": {"type": "string"}},
            "missing_metric": {
                "type": "object",
                "properties": {"description_vi": {"type": "string"}},
                "required": ["description_vi"],
            },
        },
        "required": ["answer_vi", "metrics_cited"],
    },
}


@dataclass
class AskResult:
    answer_vi: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    missing_metric: dict[str, str] | None = None
    conversation_id: str = ""
    ask_id: str = ""
    refused_reason: str | None = None
    cached: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "answer_vi": self.answer_vi,
            "citations": self.citations,
            "missing_metric": self.missing_metric,
            "conversation_id": self.conversation_id,
            "ask_id": self.ask_id,
            "refused_reason": self.refused_reason,
            "cached": self.cached,
        }


@dataclass
class ToolSession:
    tool_log: list[dict[str, Any]] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


# --------------------------------------------------------------------------- tiện ích


def cache_key(ctx: AuthContext, question: str, data_as_of: str | None) -> str:
    scope = "all" if ctx.metric_scope == "all" else ",".join(sorted(ctx.metric_scope))
    body = json.dumps(
        [ctx.tenant_id, scope, guard.normalize_question(question), data_as_of, get_registry().library_version],
        ensure_ascii=False,
    )
    return hashlib.sha256(body.encode()).hexdigest()


def description_key(text: str) -> str:
    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()[:200]


def citations_from(tool_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chân trang từ nhật ký công cụ: mọi chỉ số đã truy vấn thành công, kể cả khi model không nhắc."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for t in tool_log:
        if t["name"] != "query_metric" or t.get("error"):
            continue
        res = t.get("result") or {}
        tm = res.get("time") or {}
        for name, meta in (res.get("metrics") or {}).items():
            k = (name, str(tm.get("from")), str(tm.get("to")))
            if k in seen:
                continue
            seen.add(k)
            out.append(
                {
                    "metric": name,
                    "name_vi": meta.get("name_vi", name),
                    "version": meta.get("version", ""),
                    "time": {"from": tm.get("from"), "to": tm.get("to")},
                    "data_as_of": res.get("data_as_of"),
                }
            )
    return out


def _history(db: Session, ctx: AuthContext, conversation_id: str) -> list[dict[str, Any]]:
    q = select(AskLog).where(
        AskLog.conversation_id == conversation_id,
        AskLog.tenant_id == ctx.tenant_id,
        AskLog.answer_vi.is_not(None),
        AskLog.refused_reason.is_(None),
    )
    q = (
        q.where(AskLog.user_id == ctx.user_id)
        if ctx.telegram_link_id is None
        else q.where(AskLog.telegram_link_id == ctx.telegram_link_id)
    )
    rows = list(db.scalars(q.order_by(AskLog.created_at.desc()).limit(HISTORY_TURNS)))
    msgs: list[dict[str, Any]] = []
    for r in reversed(rows):
        msgs.append({"role": "user", "content": f"<question>{r.question_masked}</question>"})
        msgs.append({"role": "assistant", "content": r.answer_vi or ""})
    return msgs


def record_cost(db: Session, tenant_id: str, usd: Decimal) -> None:
    if usd <= 0:
        return
    rate = db.scalar(
        select(FxManualRate.rate_vnd).where(FxManualRate.currency == "USD").order_by(FxManualRate.date.desc())
    )
    vnd = (usd * (rate or USD_VND_FALLBACK)).quantize(Decimal("0.01"))
    stmt = insert(TenantCost).values(
        id=new_ulid(), month=month_start(today_vn()), tenant_id=tenant_id, item="ai", amount_vnd=vnd
    )
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=["month", "tenant_id", "item"],
            set_={"amount_vnd": TenantCost.amount_vnd + vnd, "updated_at": now_utc()},
        )
    )


def _record_missing(db: Session, tenant_id: str, question: str, description: str) -> None:
    stmt = insert(MetricRequest).values(
        id=new_ulid(),
        tenant_id=tenant_id,
        question=question,
        description_vi=description[:500],
        description_key=description_key(description) or description_key(question),
        count=1,
        status="new",
    )
    db.execute(
        stmt.on_conflict_do_update(
            constraint="uq_metric_requests_key",
            set_={"count": MetricRequest.count + 1, "question": question, "updated_at": now_utc()},
        )
    )


# --------------------------------------------------------------------------- vòng gọi model


def run_model(
    caller: ModelCaller,
    runner: ToolRunner,
    system: str,
    messages: list[dict[str, Any]],
    sess: ToolSession,
    final_tool: dict[str, Any] = FINAL_TOOL,
    time_budget: float = TIME_BUDGET_SECONDS,
) -> dict[str, Any] | None:
    """Chạy tới khi model gọi công cụ kết thúc (trả input của nó) hoặc hết lượt/thời gian (trả None)."""
    tools = [*TOOLS, final_tool]
    deadline = time.monotonic() + time_budget
    while time.monotonic() < deadline:
        res = caller(system, messages, tools)
        usage = res.get("usage") or {}
        sess.input_tokens += int(usage.get("input_tokens") or 0)
        sess.output_tokens += int(usage.get("output_tokens") or 0)
        blocks = list(res.get("content") or [])
        uses = [b for b in blocks if b.get("type") == "tool_use"]
        messages.append({"role": "assistant", "content": blocks})
        final = next((b for b in uses if b["name"] == final_tool["name"]), None)
        if final is not None:
            return dict(final.get("input") or {})
        if not uses:
            text = "".join(str(b.get("text", "")) for b in blocks if b.get("type") == "text").strip()
            return {"answer_vi": text, "metrics_cited": []} if text else None
        results: list[dict[str, Any]] = []
        for b in uses:
            entry: dict[str, Any] = {"name": b["name"], "input": b.get("input") or {}}
            if len(sess.tool_log) >= MAX_TOOL_CALLS:
                out: dict[str, Any] = {"error": "Đã hết lượt gọi công cụ. Hãy gọi final_answer ngay."}
                entry["error"] = "TOOL_LIMIT"
            else:
                try:
                    out = runner.run(b["name"], dict(b.get("input") or {}))
                    entry["result"] = out
                    if b["name"] == "query_metric":
                        sess.results.append(out)
                except ApiError as exc:
                    out = {"error": exc.code, "message": exc.detail}
                    entry["error"] = exc.code
            sess.tool_log.append(entry)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": b["id"],
                    "content": json.dumps(out, ensure_ascii=False, default=str),
                    **({"is_error": True} if "error" in out else {}),
                }
            )
        messages.append({"role": "user", "content": results})
    return None


def ask(
    db: Session,
    ctx: AuthContext,
    question: str,
    channel: Channel,
    conversation_id: str | None = None,
    *,
    caller: ModelCaller | None = None,
    runner: ToolRunner | None = None,
) -> AskResult:
    started = time.perf_counter()
    question = question.strip()[:1000]
    conv = conversation_id or new_ulid()
    masked = guard.mask(question)
    log_row = AskLog(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        telegram_link_id=ctx.telegram_link_id,
        conversation_id=conv,
        channel=channel,
        question_masked=masked,
        tool_calls=[],
        citations=[],
    )

    def finish(res: AskResult, sess: ToolSession | None = None, warnings: list[str] | None = None) -> AskResult:
        log_row.answer_vi = res.answer_vi
        log_row.citations = res.citations
        log_row.refused_reason = res.refused_reason
        log_row.latency_ms = int((time.perf_counter() - started) * 1000)
        if sess is not None:
            calls: list[dict[str, Any]] = [
                {
                    "name": t["name"],
                    "input": t["input"],
                    "error": t.get("error"),
                    "rows": len((t.get("result") or {}).get("rows") or []),
                }
                for t in sess.tool_log
            ]
            if warnings:
                calls.append({"name": "number_check", "unmatched": warnings})
                log.warning("câu trả lời có số không có trong kết quả công cụ", extra={"count": len(warnings)})
            log_row.tool_calls = calls
            log_row.input_tokens, log_row.output_tokens = sess.input_tokens, sess.output_tokens
            model = get_settings().anthropic_model_ask
            usd = cost_usd(model, sess.input_tokens, sess.output_tokens)
            log_row.cost_usd = usd
            record_cost(db, ctx.tenant_id, usd)
        db.add(log_row)
        db.flush()
        res.ask_id, res.conversation_id = log_row.id, conv
        return res

    # 2. kiểm tra trước
    reason = guard.refuse_reason(question)
    if reason:
        return finish(AskResult(guard.REFUSE_BUYER, refused_reason=reason))

    # 3. bộ nhớ đệm (chỉ câu hỏi đầu của hội thoại: câu sau phụ thuộc ngữ cảnh)
    history = _history(db, ctx, conv) if conversation_id else []
    status = data_status(ctx)
    key = cache_key(ctx, question, iso_z(status.data_as_of) if status.data_as_of else None)
    log_row.cache_key = key
    if not history:
        hit = db.scalar(
            select(AskLog)
            .where(
                AskLog.cache_key == key,
                AskLog.tenant_id == ctx.tenant_id,
                AskLog.answer_vi.is_not(None),
                AskLog.refused_reason.is_(None),
                AskLog.created_at > now_utc() - timedelta(days=CACHE_DAYS),
            )
            .order_by(AskLog.created_at.desc())
        )
        if hit is not None and hit.citations:
            log_row.tool_calls = [{"name": "cache", "ask_id": hit.id}]
            return finish(AskResult(str(hit.answer_vi), list(hit.citations), cached=True))

    model_call = caller or default_caller("ask")
    if model_call is None:
        return finish(AskResult(NO_MODEL_ANSWER, refused_reason="model_unavailable"))
    tools = runner or default_runner(ctx, db)

    # 4–6. ngữ cảnh, model, kiểm tra sau
    system = build_system(ctx, db)
    messages = [*history, {"role": "user", "content": f"<question>{question}</question>"}]
    sess = ToolSession()
    final: dict[str, Any] | None = None
    for attempt in range(2):
        try:
            final = run_model(model_call, tools, system, messages, sess)
        except ApiError:
            raise
        except Exception:
            log.exception("gọi model lỗi")
            final = None
        if final is None:
            break
        if final.get("missing_metric"):
            break
        queried = {c["metric"] for c in citations_from(sess.tool_log)}
        cited = {str(m) for m in final.get("metrics_cited") or []}
        if cited <= queried:
            break
        final = None
        if attempt == 0:
            messages.append(
                {
                    "role": "user",
                    "content": "Nhắc lại: chỉ được dùng số của chỉ số đã truy vấn bằng query_metric trong phiên này. "
                    f"Các chỉ số bạn nêu nhưng chưa truy vấn: {', '.join(sorted(cited - queried))}. "
                    "Truy vấn chúng rồi gọi final_answer.",
                }
            )
    if final is None:
        return finish(AskResult(FAILED_ANSWER, citations_from(sess.tool_log), refused_reason="answer_failed"), sess)
    if final.get("missing_metric"):
        desc = str((final.get("missing_metric") or {}).get("description_vi") or question)
        _record_missing(db, ctx.tenant_id, masked, desc)
        return finish(AskResult(MISSING_ANSWER, missing_metric={"description_vi": desc}), sess)

    answer = str(final.get("answer_vi") or "").strip() or FAILED_ANSWER
    # 7. chân trang từ nhật ký công cụ
    cites = citations_from(sess.tool_log)
    warnings = guard.unmatched_numbers(answer, sess.results)
    return finish(AskResult(answer, cites), sess, warnings)
