"""Claude so từng cặp sản phẩm (spec 10 §4 bước 3). Chỉ gửi dữ liệu sản phẩm, không bao giờ có trường người mua."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from identity_worker.candidates import Product
from identity_worker.similarity import attributes

BATCH = 20
ALLOWED_FIELDS = {"id", "source", "name", "category", "attributes", "price_vnd"}
SYSTEM = (
    "Bạn so sánh từng cặp sản phẩm bán trên các sàn thương mại điện tử Việt Nam của cùng một shop. "
    'Trả lời JSON thuần: {"results": [{"pair": <số thứ tự>, "same": true|false, "confidence": 0..1, '
    '"reason_vi": "<một câu tiếng Việt>"}]}. Hai sản phẩm là một khi cùng món hàng, cùng quy cách '
    "(dung tích, khối lượng, màu, kích cỡ); khác quy cách là khác sản phẩm."
)


@dataclass(frozen=True)
class Verdict:
    same: bool
    confidence: float
    reason_vi: str


def product_payload(p: Product) -> dict[str, Any]:
    """Payload một sản phẩm gửi cho model (NFR-03): chỉ trường sản phẩm."""
    return {
        "id": p.key,
        "source": p.source,
        "name": p.name,
        "category": p.category,
        "attributes": sorted(attributes(p.name)),
        "price_vnd": round(p.price) if p.price else None,
    }


def build_messages(pairs: list[tuple[Product, Product]]) -> list[dict[str, Any]]:
    items = [{"pair": i, "a": product_payload(a), "b": product_payload(b)} for i, (a, b) in enumerate(pairs)]
    return [{"role": "user", "content": json.dumps(items, ensure_ascii=False)}]


Caller = Callable[[str, list[dict[str, Any]]], str]


def anthropic_caller(api_key: str, model: str) -> Caller:  # pragma: no cover - gọi API thật
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    def call(system: str, messages: list[dict[str, Any]]) -> str:
        res = client.messages.create(  # type: ignore[call-overload]
            model=model, max_tokens=4000, temperature=0, system=system, messages=messages
        )
        return "".join(getattr(b, "text", "") for b in res.content)

    return call


def judge(pairs: list[tuple[Product, Product]], call: Caller) -> list[Verdict | None]:
    """Gộp tối đa 20 cặp mỗi lần gọi; cặp model không trả lời hợp lệ → None (không gợi ý)."""
    out: list[Verdict | None] = []
    for i in range(0, len(pairs), BATCH):
        chunk = pairs[i : i + BATCH]
        try:
            raw = call(SYSTEM, build_messages(chunk))
            start, end = raw.find("{"), raw.rfind("}")
            data = json.loads(raw[start : end + 1]) if start >= 0 else {}
        except (ValueError, KeyError):
            data = {}
        by_idx = {int(r.get("pair", -1)): r for r in data.get("results", []) if isinstance(r, dict)}
        for j in range(len(chunk)):
            r = by_idx.get(j)
            if r is None:
                out.append(None)
                continue
            try:
                conf = max(0.0, min(1.0, float(r.get("confidence", 0))))
            except (TypeError, ValueError):
                conf = 0.0
            out.append(Verdict(bool(r.get("same")), conf, str(r.get("reason_vi") or "")[:300]))
    return out
