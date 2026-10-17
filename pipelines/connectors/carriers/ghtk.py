"""Connector Giao Hàng Tiết Kiệm (FR-ING-09).

API: `GET {base}/services/shipment/v2/{mã vận đơn}` với header `Token` và `X-Client-Source` (mã đối tác).
Tài liệu: https://api.ghtk.vn/docs/submit-order/tracking-status. Trường người nhận trong phản hồi bị bỏ.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from connectors.base import SourceError, SyncContext, SyncOutcome
from connectors.carriers.common import SHIPMENTS, credentials, dec, latest_events, shipment_rows, since
from connectors.common.http import AuthExpired, HttpClient
from connectors.common.load import Table, run_tables
from dx_common.tenants import SourceConfig, TenantConfig
from dx_common.timeutil import VN_TZ

BASE = "https://services.giaohangtietkiem.vn"
# -1 hủy, 5 đã giao, 6 đã đối soát, 11 đã đối soát trả hàng, 21 đã trả hàng
FINAL = {"-1", "6", "11", "21"}


class GhtkClient(HttpClient):
    def __init__(self, token: str, partner_code: str, base: str = BASE, **kw: Any) -> None:
        super().__init__(base, **kw)
        self.headers = {"Token": token}
        if partner_code:
            self.headers["X-Client-Source"] = partner_code

    def check(self, resp: httpx.Response, body: Any) -> None:
        if isinstance(body, dict) and body.get("success") is False and "token" in str(body.get("message", "")).lower():
            raise AuthExpired()
        super().check(resp, body)

    def status(self, waybill: str) -> dict[str, Any] | None:
        try:
            body = self.send("GET", f"/services/shipment/v2/{waybill}", headers=self.headers)
        except AuthExpired as exc:
            raise SourceError("auth_revoked", "GHTK: token không hợp lệ") from exc
        except SourceError as exc:
            if exc.reason == "api_error":
                return None
            raise
        o = (body or {}).get("order") or {}
        if not o:
            return None
        return {
            "client_order_code": o.get("partner_id"),
            "status_raw": None if o.get("status") is None else str(o.get("status")),
            "updated_at": _ts(o.get("modified")),
            "shipping_fee": dec(o.get("ship_money")),
            "cod_amount": dec(o.get("pick_money")),
            "insurance_fee": dec(o.get("insurance")),
            "weight_g": o.get("weight"),
        }


def _ts(v: Any) -> datetime | None:
    if not v:
        return None
    return datetime.strptime(str(v)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=VN_TZ)


def sync_ghtk(tenant: TenantConfig, source: SourceConfig, ctx: SyncContext) -> SyncOutcome:
    client: GhtkClient | None = ctx.extra.get("ghtk_client")
    if client is None:
        cred = credentials(source.secret_ref or "")
        client = GhtkClient(str(cred["token"]), str(cred.get("partner_code") or ""))
    events = ctx.extra.get("ghtk_events") or latest_events(tenant.tenant_id, "ghtk", since(ctx.now))
    rows = shipment_rows(events, FINAL, client.status)
    return run_tables(tenant, source, ctx, [Table("ghtk__shipments", ["waybill"], lambda st: rows, SHIPMENTS)])
