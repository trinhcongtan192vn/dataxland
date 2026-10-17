"""Connector Giao Hàng Nhanh (FR-ING-09).

API: `POST {base}/shiip/public-api/v2/shipping-order/detail` với header `Token`, `ShopId`, body `{"order_code"}`.
Tài liệu: https://developer.ghn.vn. Môi trường thử: `https://dev-online-gateway.ghn.vn`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from connectors.base import SourceError, SyncContext, SyncOutcome
from connectors.carriers.common import SHIPMENTS, credentials, dec, latest_events, shipment_rows, since
from connectors.common.http import AuthExpired, HttpClient
from connectors.common.load import Table, run_tables
from dx_common.tenants import SourceConfig, TenantConfig

BASE = "https://online-gateway.ghn.vn"
FINAL = {"delivered", "returned", "cancel", "lost", "damage"}


class GhnClient(HttpClient):
    def __init__(self, token: str, shop_id: str, base: str = BASE, **kw: Any) -> None:
        super().__init__(base, **kw)
        self.headers = {"Token": token, "ShopId": str(shop_id), "Content-Type": "application/json"}

    def check(self, resp: httpx.Response, body: Any) -> None:
        if resp.status_code == 400 and isinstance(body, dict) and "token" in str(body.get("message", "")).lower():
            raise AuthExpired()
        super().check(resp, body)

    def detail(self, waybill: str) -> dict[str, Any] | None:
        try:
            body = self.send(
                "POST", "/shiip/public-api/v2/shipping-order/detail", json={"order_code": waybill}, headers=self.headers
            )
        except AuthExpired as exc:
            raise SourceError("auth_revoked", "GHN: token không hợp lệ") from exc
        except SourceError as exc:
            if exc.reason == "api_error":  # vận đơn không còn tra được: giữ số từ webhook
                return None
            raise
        d = (body or {}).get("data") or {}
        if not d:
            return None
        fee = d.get("fee") or {}
        return {
            "client_order_code": d.get("client_order_code"),
            "status_raw": d.get("status"),
            "updated_at": _ts(d.get("updated_date")),
            "shipping_fee": dec(d.get("total_fee") if d.get("total_fee") is not None else fee.get("main_service")),
            "cod_amount": dec(d.get("cod_amount")),
            "return_fee": dec(fee.get("return")),
            "insurance_fee": dec(fee.get("insurance")),
            "weight_g": d.get("weight"),
        }


def _ts(v: Any) -> datetime | None:
    if not v:
        return None
    ts = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def sync_ghn(tenant: TenantConfig, source: SourceConfig, ctx: SyncContext) -> SyncOutcome:
    client: GhnClient | None = ctx.extra.get("ghn_client")
    if client is None:
        cred = credentials(source.secret_ref or "")
        client = GhnClient(str(cred["token"]), str(cred.get("shop_id") or source.account_id or ""))
    events = ctx.extra.get("ghn_events") or latest_events(tenant.tenant_id, "ghn", since(ctx.now))
    rows = shipment_rows(events, FINAL, client.detail)
    return run_tables(tenant, source, ctx, [Table("ghn__shipments", ["waybill"], lambda st: rows, SHIPMENTS)])
