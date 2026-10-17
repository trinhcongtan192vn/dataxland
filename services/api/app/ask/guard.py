"""Kiểm tra trước và sau của bộ máy hỏi đáp (spec 09 §5, FR-TG-08).

- Trước: câu hỏi về một người mua cụ thể bị từ chối ngay, không gọi model.
- Che số điện thoại, email trước khi lưu câu hỏi (spec 09 §6).
- Sau: so số trong câu trả lời với số trong kết quả công cụ; số lạ chỉ ghi cảnh báo.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable
from typing import Any

REFUSE_BUYER = "DataxLand không cung cấp thông tin về từng người mua."

_PHONE = re.compile(r"(?<!\d)(?:\+?84|0)(?:[\s.\-]?\d){8,10}(?!\d)")
_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
_ORDER_ID = re.compile(r"\b\d{6,}[A-Z]{1,4}\b|\b\d{12,}\b")
_ORDER_KW = re.compile(r"(mã đơn|đơn hàng số|đơn số|order id|order_sn)\s*[:#]?\s*\w*\d", re.I)
_BUYER = r"(khách(?:\s+hàng)?|người\s+mua|người\s+đặt|buyer)"
_ATTR = re.compile(
    r"(số\s+điện\s+thoại|điện\s+thoại|\bsđt\b|\bsdt\b|e-?mail|địa\s+chỉ|\bzalo\b|họ\s+tên|tên\s+thật)", re.I
)
_WHO = re.compile(rf"{_BUYER}\s+(nào|tên|là\s+ai)|\bai\s+(đã\s+)?(mua|đặt)|tên\s+(của\s+)?{_BUYER}", re.I)
_NAMED = re.compile(r"\b(?i:khách|người mua|anh|chị|cô|chú)\s+(?i:tên\s+)?[A-ZĐ][a-zà-ỹđ]+")


def refuse_reason(question: str) -> str | None:
    """Trả mã lý do khi câu hỏi nhắm vào một người mua cụ thể (spec 09 §5)."""
    q = unicodedata.normalize("NFC", question)
    if _PHONE.search(q) or _EMAIL.search(q):
        return "buyer_contact"
    if _ORDER_ID.search(q) or _ORDER_KW.search(q):
        return "order_id"
    if _ATTR.search(q) and re.search(_BUYER, q, re.I):
        return "buyer_pii"
    if _WHO.search(q) or _NAMED.search(q):
        return "buyer_named"
    return None


def mask(question: str) -> str:
    q = _EMAIL.sub("[đã che]", question)
    return _PHONE.sub("[đã che]", q)


def normalize_question(question: str) -> str:
    q = unicodedata.normalize("NFC", question).lower().strip()
    q = re.sub(r"[?!.。…]+$", "", q)
    return re.sub(r"\s+", " ", q)


# --------------------------------------------------------------------------- kiểm tra số

_NUM = re.compile(
    r"(?<![\w/])(-?\d{1,3}(?:\.\d{3})+(?:,\d+)?|-?\d+(?:,\d+)?)\s*(%|₫|đ\b|tỷ|tỉ|triệu|tr\b|nghìn|ngàn|k\b)?",
    re.I,
)
_MULT = {"tỷ": 1e9, "tỉ": 1e9, "triệu": 1e6, "tr": 1e6, "nghìn": 1e3, "ngàn": 1e3, "k": 1e3}


def answer_numbers(text: str) -> list[tuple[float, float, str]]:
    """Các số trong câu trả lời: (giá trị, sai số làm tròn, chuỗi gốc). Bỏ năm, ngày tháng và số nhỏ không đơn vị."""
    out: list[tuple[float, float, str]] = []
    for m in _NUM.finditer(text):
        raw, unit = m.group(1), (m.group(2) or "").lower()
        end = m.end(1)
        if end < len(text) and text[end] == "/":
            continue
        dec = raw.split(",")[1] if "," in raw else ""
        value = float(raw.replace(".", "").replace(",", "."))
        mult = _MULT.get(unit, 1.0)
        if not unit and (abs(value) <= 12 or (1900 <= value <= 2100 and not dec)):
            continue
        tol = 0.5 * 10 ** (-len(dec)) * mult
        out.append((value * mult, tol, m.group(0).strip()))
    return out


def _walk(obj: Any) -> Iterable[float]:
    if isinstance(obj, bool):
        return
    if isinstance(obj, int | float):
        if math.isfinite(obj):
            yield float(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k not in ("time", "data_as_of", "warnings", "date"):
                yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def tool_numbers(results: list[dict[str, Any]], cap: int = 80) -> list[float]:
    """Số từ kết quả công cụ cùng các phép tính đơn giản giữa chúng (hiệu, tỷ lệ, % thay đổi, tổng)."""
    base: list[float] = []
    for r in results:
        base.extend(_walk(r.get("rows", [])))
    base = base[:cap]
    cands = set(base)
    cands.update(v * 100 for v in base)
    cands.add(sum(base))
    for a in base:
        for b in base:
            if a is b:
                continue
            cands.add(a - b)
            if b:
                cands.add(a / b)
                cands.add(a / b * 100)
                cands.add((a - b) / b * 100)
    return list(cands)


def unmatched_numbers(answer: str, results: list[dict[str, Any]]) -> list[str]:
    nums = answer_numbers(answer)
    if not nums:
        return []
    cands = tool_numbers(results)
    bad: list[str] = []
    for value, tol, raw in nums:
        if not any(abs(abs(value) - abs(c)) <= max(tol, 0.006 * abs(c)) for c in cands):
            bad.append(raw)
    return bad
