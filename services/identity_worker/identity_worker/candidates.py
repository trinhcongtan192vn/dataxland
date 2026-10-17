"""Ứng viên ghép (spec 10 §2) đọc từ `t_<id>_stg` của khách. Chỉ đọc cột băm của người mua (NFR-03)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

SALES = ("shopee", "tiktok_shop", "lazada", "amazon_seller")


class Warehouse(Protocol):
    kind: str

    def list_tables(self, dataset: str) -> list[str]: ...
    def query(self, sql: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]: ...
    def write_rows(self, dataset: str, table: str, columns: dict[str, str], rows: list[dict[str, Any]]) -> int: ...


@dataclass(frozen=True)
class Product:
    source: str
    source_id: str
    seller_sku: str | None
    name: str | None
    barcode: str | None
    category: str | None
    price: float | None = None  # giá bán trung vị 30 ngày theo SKU trên kênh đó
    revenue_90d: float = 0.0

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"


@dataclass(frozen=True)
class OrderRef:
    source: str
    source_id: str
    buyer_ref: str | None
    phone_hash: str | None
    email_hash: str | None
    ordered_at: str


@dataclass
class Candidates:
    products: list[Product] = field(default_factory=list)
    orders: list[OrderRef] = field(default_factory=list)


def _q(wh: Warehouse, name: str) -> str:
    return f'"{name}"' if wh.kind == "duckdb" else f"`{name}`"


def load(wh: Warehouse, prefix: str, sources: list[str], today: str) -> Candidates:
    stg = f"{prefix}_stg"
    marts = f"{prefix}_marts"
    have = set(wh.list_tables(stg))
    out = Candidates()
    prices: dict[tuple[str, str], float] = {}
    revenue: dict[str, float] = {}
    for src in sources:
        lines = f"stg_{src}__order_lines"
        if lines in have:
            # Giá trung vị 30 ngày gần nhất theo SKU (giá dòng / số lượng), tính ở Python để chạy mọi kho.
            rows = wh.query(
                f"select l.seller_sku, l.unit_price_vnd from {_q(wh, stg)}.{_q(wh, lines)} as l "
                f"join {_q(wh, stg)}.{_q(wh, f'stg_{src}__orders')} as o on o.source_id = l.order_source_id "
                f"where o.order_date >= cast('{today}' as date) - interval 30 day"
                if wh.kind == "duckdb"
                else f"select l.seller_sku, l.unit_price_vnd from {_q(wh, stg)}.{_q(wh, lines)} as l "
                f"join {_q(wh, stg)}.{_q(wh, f'stg_{src}__orders')} as o on o.source_id = l.order_source_id "
                f"where o.order_date >= date_sub(date '{today}', interval 30 day)"
            )
            by_sku: dict[str, list[float]] = {}
            for sku, price in rows:
                if sku and price is not None:
                    by_sku.setdefault(str(sku).strip().lower(), []).append(float(price))
            for sku, vals in by_sku.items():
                vals.sort()
                prices[(src, sku)] = vals[len(vals) // 2]
        products = f"stg_{src}__products"
        if products in have:
            for sid, sku, name, barcode, cat in wh.query(
                f"select source_id, seller_sku, name, barcode, category_raw from {_q(wh, stg)}.{_q(wh, products)}"
            ):
                key = (src, str(sku or "").strip().lower())
                out.products.append(Product(src, str(sid), sku, name, barcode, cat, prices.get(key)))
        orders = f"stg_{src}__orders"
        if orders in have:
            for sid, ref, ph, em, at in wh.query(
                f"select source_id, buyer_ref, buyer_phone_hash, buyer_email_hash, cast(ordered_at as varchar) "
                f"from {_q(wh, stg)}.{_q(wh, orders)}"
                if wh.kind == "duckdb"
                else f"select source_id, buyer_ref, buyer_phone_hash, buyer_email_hash, cast(ordered_at as string) "
                f"from {_q(wh, stg)}.{_q(wh, orders)}"
            ):
                out.orders.append(OrderRef(src, str(sid), ref, ph, em, str(at or "")))
    if "mrt_seller__order_lines" in set(wh.list_tables(marts)):
        for sku, rev in wh.query(
            f"select lower(trim(seller_sku)), sum(net_revenue_vnd) from {_q(wh, marts)}.mrt_seller__order_lines "
            "group by 1"
        ):
            if sku:
                revenue[str(sku)] = float(rev or 0)
    out.products = [
        Product(
            p.source,
            p.source_id,
            p.seller_sku,
            p.name,
            p.barcode,
            p.category,
            p.price,
            revenue.get(str(p.seller_sku or "").strip().lower(), 0.0),
        )
        for p in out.products
    ]
    return out
