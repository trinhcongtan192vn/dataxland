"""Ghi `identity_map` (spec 10 §6): nhóm liên thông từ cặp đã duyệt, `canonical_id` ổn định giữa các lần chạy."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from identity_worker.candidates import OrderRef, Product
from identity_worker.rules import Pair

COLUMNS = {
    "entity": "string",
    "source": "string",
    "source_id": "string",
    "canonical_id": "string",
    "method": "string",
    "approved_by": "string",
    "approved_at": "timestamp",
}
NULL = "_dbt_utils_surrogate_key_null_"


def surrogate(*parts: Any) -> str:
    """Như `dbt_utils.generate_surrogate_key`: md5 của các trường nối bằng '-', null thay bằng hằng."""
    return hashlib.md5("-".join(NULL if p is None else str(p) for p in parts).encode()).hexdigest()  # noqa: S324


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)

    def groups(self) -> list[list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        for x in list(self.parent):
            out[self.find(x)].append(x)
        return [sorted(v) for v in out.values() if len(v) > 1]


def assign_canonical(groups: list[list[str]], prev: dict[str, str], fresh: dict[str, str]) -> dict[str, str]:
    """Nhóm giữ `canonical_id` cũ (nhóm lớn hơn được ưu tiên khi bị tách); nhóm mới lấy `fresh` của thành viên."""
    used: set[str] = set()
    out: dict[str, str] = {}
    for g in sorted(groups, key=len, reverse=True):
        counts: dict[str, int] = defaultdict(int)
        for m in g:
            if m in prev:
                counts[prev[m]] += 1
        canon = next((c for c, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if c not in used), None)
        if canon is None:
            canon = fresh[g[0]]
        used.add(canon)
        for m in g:
            out[m] = canon
    return out


def product_map(products: list[Product], approved: list[Pair], prev: dict[str, str]) -> dict[str, str]:
    """`canonical_id` của sản phẩm là `product_id` (khóa SKU của GĐ1) của thành viên có doanh thu 90 ngày lớn nhất."""
    by_key = {p.key: p for p in products}
    uf = UnionFind()
    for pr in approved:
        if pr.left in by_key and pr.right in by_key:
            uf.union(pr.left, pr.right)
    groups = uf.groups()
    fresh: dict[str, str] = {}
    for g in groups:
        top = max(g, key=lambda k: (by_key[k].revenue_90d, k))
        p = by_key[top]
        sku = (p.seller_sku or "").strip().lower()
        canon = surrogate(sku) if sku else surrogate(p.source, p.source_id)
        for m in g:
            fresh[m] = canon
    return assign_canonical(groups, prev, fresh)


def customer_map(orders: list[OrderRef], pairs: list[Pair], prev: dict[str, str]) -> dict[str, str]:
    """`canonical_id` của người mua là khóa băm (như `int_orders.customer_id`) của thành viên có đơn sớm nhất."""
    by_key = {f"{o.source}:{o.source_id}": o for o in orders}
    uf = UnionFind()
    for pr in pairs:
        if pr.left in by_key and pr.right in by_key:
            uf.union(pr.left, pr.right)
    groups = uf.groups()
    fresh: dict[str, str] = {}
    for g in groups:
        first = min((by_key[k] for k in g), key=lambda o: (o.ordered_at, o.source, o.source_id))
        if first.buyer_ref:
            canon = surrogate(first.source, first.buyer_ref)
        elif first.phone_hash:
            canon = surrogate(first.phone_hash)
        else:
            canon = surrogate(first.source, first.source_id)
        for m in g:
            fresh[m] = canon
    return assign_canonical(groups, prev, fresh)


def rows(entity: str, mapping: dict[str, str], methods: dict[str, str], approved_at: Any) -> list[dict[str, Any]]:
    out = []
    for member, canon in sorted(mapping.items()):
        source, _, source_id = member.partition(":")
        out.append(
            {
                "entity": entity,
                "source": source,
                "source_id": source_id,
                "canonical_id": canon,
                "method": methods.get(member, "rule"),
                "approved_by": "system" if entity == "customer" else None,
                "approved_at": approved_at,
            }
        )
    return out
