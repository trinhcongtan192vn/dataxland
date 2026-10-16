"""Connector TikTok Shop (spec 01 §4, FR-ING-02)."""

from __future__ import annotations

from connectors.base import SyncContext, SyncOutcome
from connectors.common.load import Table, open_orders, run_tables
from connectors.common.tokens import TokenManager, load_app
from connectors.tiktok_shop import resources as r
from connectors.tiktok_shop import schema as cols
from connectors.tiktok_shop.client import AUTH_BASE, TikTokClient, TikTokHttp, refresh_token
from dx_common.tenants import SourceConfig, TenantConfig
from dx_common.tenants.naming import source_secret


def build_client(tenant: TenantConfig, source: SourceConfig, ctx: SyncContext) -> TikTokClient:
    app = load_app("tiktok_shop")
    http = ctx.extra.get("tiktok_http")
    auth_http = http or TikTokHttp(str(app.get("auth_base") or AUTH_BASE))
    secret = source.secret_ref or source_secret(tenant.tenant_id, "tiktok_shop", source.account_id or "")
    tokens = TokenManager(secret, app, lambda a, d: refresh_token(a, d, auth_http), clock=lambda: ctx.now)
    tokens.ensure_fresh()
    return TikTokClient(tokens, http, clock=lambda: ctx.now.timestamp())


def sync_tiktok_shop(tenant: TenantConfig, source: SourceConfig, ctx: SyncContext) -> SyncOutcome:
    c = build_client(tenant, source, ctx)
    account = source.account_id or ""
    rescan = open_orders(ctx, "tiktok_shop__orders", "id", "status", "create_time", r.FINAL, account)
    f = r.OrderFetcher(c, ctx.now, rescan)
    tables = [
        Table("tiktok_shop__orders", ["id"], f.orders, cols.ORDERS),
        Table("tiktok_shop__order_items", ["order_id", "id"], f.items, cols.ORDER_ITEMS),
        Table("tiktok_shop__settlements", ["order_id", "transaction_id"], f.settlements, cols.SETTLEMENTS),
        Table("tiktok_shop__returns", ["return_id"], lambda st: r.returns(c, ctx.now, st), cols.RETURNS),
        Table("tiktok_shop__products", ["product_id", "sku_id"], lambda st: r.products(c), cols.PRODUCTS),
        Table("tiktok_shop__daily_totals", ["date"], lambda st: r.daily_totals(c, ctx.now, st), cols.DAILY_TOTALS),
    ]
    return run_tables(tenant, source, ctx, tables)
