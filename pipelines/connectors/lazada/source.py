"""Connector Lazada (spec 01 §5, FR-ING-03)."""

from __future__ import annotations

from connectors.base import SyncContext, SyncOutcome
from connectors.common.load import Table, run_tables
from connectors.common.tokens import TokenManager, load_app
from connectors.lazada import resources as r
from connectors.lazada.client import LazadaClient, LazadaHttp, refresh_token
from dx_common.marketplace import LAZADA_AUTH
from dx_common.tenants import SourceConfig, TenantConfig
from dx_common.tenants.naming import source_secret

ORDERS = {
    "order_id": "string",
    "created_at": "string",
    "updated_at": "string",
    "statuses": "string",
    "currency": "string",
    "price": "numeric",
    "shipping_fee": "numeric",
    "voucher_seller": "numeric",
    "voucher_platform": "numeric",
    "customer_first_name": "string",
    "address_phone": "string",
    "address_full": "string",
}
ORDER_ITEMS = {
    "order_item_id": "string",
    "order_id": "string",
    "name": "string",
    "sku": "string",
    "shop_sku": "string",
    "item_price": "numeric",
    "paid_price": "numeric",
    "voucher_seller": "numeric",
    "voucher_platform": "numeric",
    "status": "string",
    "created_at": "string",
    "updated_at": "string",
}
TRANSACTIONS = {
    "transaction_id": "string",
    "transaction_date": "date",
    "transaction_type": "string",
    "fee_name": "string",
    "amount": "numeric",
    "order_no": "string",
    "order_item_no": "string",
}
RETURNS = {
    "reverse_order_id": "string",
    "order_id": "string",
    "order_item_id": "string",
    "created_at": "string",
    "reason_text": "string",
    "refund_amount": "numeric",
    "status": "string",
}
PRODUCTS = {
    "item_id": "int",
    "sku_id": "int",
    "seller_sku": "string",
    "name": "string",
    "primary_category": "string",
    "ean_code": "string",
}
DAILY_TOTALS = {"date": "date", "order_count": "int", "gross_amount": "numeric", "currency": "string"}


def build_client(tenant: TenantConfig, source: SourceConfig, ctx: SyncContext) -> LazadaClient:
    app = load_app("lazada")
    http = ctx.extra.get("lazada_http")
    auth_http = http or LazadaHttp(str(app.get("auth_base") or LAZADA_AUTH))
    secret = source.secret_ref or source_secret(tenant.tenant_id, "lazada", source.account_id or "")
    tokens = TokenManager(secret, app, lambda a, d: refresh_token(a, d, auth_http), clock=lambda: ctx.now)
    tokens.ensure_fresh()
    return LazadaClient(tokens, http, clock=lambda: ctx.now.timestamp())


def sync_lazada(tenant: TenantConfig, source: SourceConfig, ctx: SyncContext) -> SyncOutcome:
    c = build_client(tenant, source, ctx)
    rescan = _open_recent(ctx, source.account_id or "")
    f = r.OrderFetcher(c, ctx.now, rescan)
    tables = [
        Table("lazada__orders", ["order_id"], f.orders, ORDERS),
        Table("lazada__order_items", ["order_item_id"], f.items, ORDER_ITEMS),
        Table("lazada__transactions", ["transaction_id"], lambda st: r.transactions(c, ctx.now, st), TRANSACTIONS),
        Table("lazada__returns", ["reverse_order_id", "order_item_id"], lambda st: r.returns(c, st), RETURNS),
        Table("lazada__products", ["item_id", "sku_id"], lambda st: r.products(c), PRODUCTS),
        Table("lazada__daily_totals", ["date"], lambda st: r.daily_totals(c, ctx.now, st), DAILY_TOTALS),
    ]
    return run_tables(tenant, source, ctx, tables)


def _open_recent(ctx: SyncContext, account: str) -> list[str]:
    """Đơn Lazada tạo trong 30 ngày, trạng thái chưa cuối (FR-ING-07). `created_at` là chuỗi có múi giờ."""
    from datetime import timedelta

    if "lazada__orders" not in ctx.warehouse.list_tables(ctx.raw_dataset):
        return []
    since = (ctx.now - timedelta(days=30)).strftime("%Y-%m-%d")
    q = '"' if ctx.warehouse.kind == "duckdb" else "`"
    fq = f"{q}{ctx.raw_dataset}{q}.{q}lazada__orders{q}"
    rows = ctx.warehouse.query(
        f"select order_id, statuses from (select order_id, statuses, row_number() over (partition by order_id "
        f"order by _dx_loaded_at desc) as rn from {fq} where substr(created_at, 1, 10) >= '{since}' "
        f"and _dx_source_account = '{account}') as x where rn = 1"
    )
    return sorted(str(k) for k, s in rows if str(s).upper() not in r.FINAL)
