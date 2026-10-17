"""Ghép theo quy tắc, tự duyệt (spec 10 §3)."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from identity_worker.candidates import OrderRef, Product


@dataclass(frozen=True)
class Pair:
    entity: str
    left: str  # "<source>:<source_id>"
    right: str
    method: str
    score: float = 1.0
    reason_vi: str | None = None

    @property
    def key(self) -> str:
        a, b = sorted((self.left, self.right))
        return f"{a}|{b}"


def norm_barcode(v: str | None) -> str | None:
    if not v:
        return None
    s = re.sub(r"\s+", "", str(v))
    return s if re.fullmatch(r"\d{8,14}", s) else None


def norm_sku(v: str | None) -> str | None:
    if not v:
        return None
    s = re.sub(r"[\s\-_.]", "", str(v).lower())
    return s or None


def _chain(items: list[str], entity: str, method: str) -> list[Pair]:
    """Nối các thành viên cùng khóa thành chuỗi cặp (đủ để union-find ra cùng nhóm)."""
    items = sorted(set(items))
    return [Pair(entity, items[0], other, method) for other in items[1:]]


def product_rules(products: list[Product]) -> list[Pair]:
    by_barcode: dict[str, list[str]] = defaultdict(list)
    by_sku: dict[str, list[str]] = defaultdict(list)
    for p in products:
        if bc := norm_barcode(p.barcode):
            by_barcode[bc].append(p.key)
        if sk := norm_sku(p.seller_sku):
            by_sku[sk].append(p.key)
    out: list[Pair] = []
    for keys in by_barcode.values():
        out += _chain(keys, "product", "rule_barcode")
    for keys in by_sku.values():
        out += _chain(keys, "product", "rule_sku")
    seen: set[str] = set()
    uniq: list[Pair] = []
    for pr in out:
        if pr.key not in seen:
            seen.add(pr.key)
            uniq.append(pr)
    return uniq


def customer_rules(orders: list[OrderRef]) -> list[Pair]:
    """Người mua chỉ ghép bằng quy tắc (FR-ID-02): cùng `phone_hash`, `email_hash`, hoặc cùng nguồn + `buyer_ref`."""
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for o in orders:
        k = f"{o.source}:{o.source_id}"
        if o.phone_hash:
            groups[("rule_phone", o.phone_hash)].append(k)
        if o.email_hash:
            groups[("rule_email", o.email_hash)].append(k)
        if o.buyer_ref:
            groups[("rule_buyer_ref", f"{o.source}:{o.buyer_ref}")].append(k)
    out: list[Pair] = []
    for (method, _), keys in groups.items():
        if len(set(keys)) > 1:
            out += _chain(keys, "customer", method)
    return out
