"""Connector Shopee (spec 01 §3, FR-ING-01)."""

from __future__ import annotations

from connectors.base import SyncContext, SyncOutcome
from connectors.common.load import Table, open_orders, run_tables
from connectors.common.tokens import TokenManager, load_app
from connectors.shopee import resources as r
from connectors.shopee import schema as cols
from connectors.shopee.client import ShopeeClient, ShopeeHttp, refresh_token
from dx_common.tenants import SourceConfig, TenantConfig
from dx_common.tenants.naming import source_secret


def build_client(tenant: TenantConfig, source: SourceConfig, ctx: SyncContext) -> ShopeeClient:
    app = load_app("shopee")
    http = ctx.extra.get("shopee_http") or ShopeeHttp(str(app.get("api_base") or "https://partner.shopeemobile.com"))
    secret = source.secret_ref or source_secret(tenant.tenant_id, "shopee", source.account_id or "")
    tokens = TokenManager(secret, app, lambda a, d: refresh_token(a, d, http), clock=lambda: ctx.now)
    tokens.ensure_fresh()
    return ShopeeClient(tokens, http, clock=lambda: ctx.now.timestamp())


def sync_shopee(tenant: TenantConfig, source: SourceConfig, ctx: SyncContext) -> SyncOutcome:
    c = build_client(tenant, source, ctx)
    account = source.account_id or ""
    rescan = open_orders(ctx, "shopee__orders", "order_sn", "order_status", "create_time", r.FINAL, account)
    f = r.OrderFetcher(c, ctx.now, rescan)
    tables = [
        Table("shopee__orders", ["order_sn"], f.orders, cols.ORDERS),
        Table("shopee__order_items", ["order_sn", "item_id", "model_id"], f.items, cols.ORDER_ITEMS),
        Table("shopee__escrow", ["order_sn"], f.escrow, cols.ESCROW),
        Table("shopee__returns", ["return_sn"], lambda st: r.returns(c, ctx.now, st), cols.RETURNS),
        Table("shopee__products", ["item_id", "model_id"], lambda st: r.products(c), cols.PRODUCTS),
        Table("shopee__daily_totals", ["date"], lambda st: r.daily_totals(c, ctx.now, st), cols.DAILY_TOTALS),
    ]
    return run_tables(tenant, source, ctx, tables)
