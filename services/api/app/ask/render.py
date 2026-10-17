"""Định dạng câu trả lời (spec 09 §3.2): Markdown cho cổng, HTML có giới hạn 4.096 ký tự mỗi tin cho Telegram.

Chân trang tự sinh từ nhật ký gọi công cụ, không do model viết.
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime
from typing import Any

from dx_common.timeutil import format_as_of, format_date_vn

TG_LIMIT = 4096


def _period(t: dict[str, Any] | None) -> str:
    if not t or not t.get("from"):
        return ""
    a, b = date.fromisoformat(str(t["from"])), date.fromisoformat(str(t["to"]))
    return format_date_vn(a) if a == b else f"{format_date_vn(a)} – {format_date_vn(b)}"


def _as_of(v: str | None) -> str:
    if not v:
        return ""
    return format_as_of(datetime.fromisoformat(v.replace("Z", "+00:00")))


def footer_lines(citations: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for c in citations:
        parts = [f"{c['name_vi']} (v{c['version']})"]
        if p := _period(c.get("time")):
            parts.append(p)
        if a := _as_of(c.get("data_as_of")):
            parts.append(f"cập nhật lúc {a}")
        out.append(" · ".join(parts))
    return out


def to_markdown(answer: str, citations: list[dict[str, Any]]) -> str:
    lines = footer_lines(citations)
    if not lines:
        return answer
    return answer + "\n\n---\n" + "\n".join(f"- {line}" for line in lines)


def _md_to_html(text: str) -> str:
    s = html.escape(text, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    return re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", s)


def to_telegram(answer: str, citations: list[dict[str, Any]]) -> list[str]:
    """Các tin HTML, mỗi tin ≤ 4.096 ký tự; chân trang ở tin cuối."""
    body = _md_to_html(answer)
    foot = "\n".join(f"<i>{html.escape(line, quote=False)}</i>" for line in footer_lines(citations))
    full = body + ("\n\n" + foot if foot else "")
    if len(full) <= TG_LIMIT:
        return [full]
    chunks: list[str] = []
    cur = ""
    for para in full.split("\n"):
        while len(para) > TG_LIMIT:
            chunks.append(para[:TG_LIMIT])
            para = para[TG_LIMIT:]
        if len(cur) + len(para) + 1 > TG_LIMIT:
            chunks.append(cur)
            cur = para
        else:
            cur = f"{cur}\n{para}" if cur else para
    if cur:
        chunks.append(cur)
    return chunks
