"""Tỷ giá Vietcombank (spec 01 §6, FR-MOD-03). Chạy hằng ngày 18:30 giờ Việt Nam (job `fx_daily`).

- Đọc XML công khai ở `FX_VCB_URL`: `<Exrate CurrencyCode="USD" Buy=".." Transfer=".." Sell=".."/>`. Lấy cột `Sell`
  (bán ra; Vietcombank dùng chung một giá bán cho tiền mặt và chuyển khoản).
- Ghép tỷ giá nhập tay (`fx_manual_rates`, `source = manual`) để staging ưu tiên.
- Ghi `merge` vào `dx_ref.fx_rates` theo (`date`, `currency`, `source`). Không điền ngày trống (việc của spec 02).
- Lỗi: phát `sync.failed` với `tenant_id = null`, `source = fx_vcb`.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET  # chỉ dùng kiểu ParseError
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from defusedxml import ElementTree as SafeET

from connectors.base import SourceError, SyncContext, SyncOutcome
from connectors.common.load import Table, run_dlt
from dx_common.config import Settings, get_settings
from dx_common.logging import get_logger
from dx_common.timeutil import VN_TZ, now_utc

log = get_logger(__name__)
DATASET = "dx_ref"
SCHEMA = {"date": "date", "currency": "string", "rate_vnd": "numeric", "source": "string"}


def parse_vcb(xml_text: str, currencies: list[str]) -> tuple[date | None, dict[str, Decimal]]:
    root = SafeET.fromstring(xml_text)
    d: date | None = None
    dt = root.findtext("DateTime")
    if dt:
        for fmt in ("%m/%d/%Y %I:%M:%S %p", "%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
            try:
                d = datetime.strptime(dt.strip(), fmt).date()
                break
            except ValueError:
                continue
    rates: dict[str, Decimal] = {}
    for ex in root.iter("Exrate"):
        code = (ex.get("CurrencyCode") or "").strip().upper()
        if code not in currencies:
            continue
        raw = (ex.get("Sell") or ex.get("Transfer") or "").replace(",", "").strip()
        try:
            v = Decimal(raw)
        except InvalidOperation:
            continue
        if v > 0:
            rates[code] = v
    return d, rates


def fetch(settings: Settings, http: httpx.Client | None = None) -> tuple[date, dict[str, Decimal]]:
    c = http or httpx.Client(timeout=30)
    try:
        r = c.get(settings.fx_vcb_url)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise SourceError("api_error", f"không tải được tỷ giá: {type(exc).__name__}") from exc
    currencies = [x.strip().upper() for x in settings.fx_currencies.split(",") if x.strip()]
    try:
        d, rates = parse_vcb(r.text, currencies)
    except ET.ParseError as exc:
        raise SourceError("api_error", "XML tỷ giá không đọc được") from exc
    missing = [c for c in currencies if c not in rates]
    if missing:
        raise SourceError("api_error", f"thiếu tỷ giá {', '.join(missing)}")
    return d or now_utc().astimezone(VN_TZ).date(), rates


def manual_rates() -> list[dict[str, Any]]:
    from sqlalchemy import text

    from dx_common.db import get_engine

    try:
        with get_engine().connect() as conn:
            rows = conn.execute(text("select date, currency, rate_vnd from fx_manual_rates"))
            return [{"date": r[0], "currency": r[1], "rate_vnd": r[2], "source": "manual"} for r in rows]
    except Exception as exc:  # Postgres chưa sẵn sàng: vẫn nạp tỷ giá VCB
        log.warning("không đọc được tỷ giá nhập tay", extra={"error": type(exc).__name__})
        return []


def sync_fx(
    ctx: SyncContext, settings: Settings | None = None, http: httpx.Client | None = None, include_manual: bool = True
) -> SyncOutcome:
    s = settings or get_settings()
    d, rates = fetch(s, http)
    rows = [{"date": d, "currency": cur, "rate_vnd": v, "source": "vcb"} for cur, v in sorted(rates.items())]
    if include_manual:
        rows += manual_rates()
    ctx.warehouse.ensure_dataset(DATASET, {"dx_kind": "reference"})
    table = Table("fx_rates", ["date", "currency", "source"], lambda st: rows, SCHEMA)
    return run_dlt("dx_ref__fx_vcb", "fx_vcb", DATASET, "vcb", ctx, [table])


def run_fx_daily(
    settings: Settings | None = None, warehouse: Any = None, api: Any = None, http: httpx.Client | None = None
) -> dict[str, Any]:
    from dx_pipelines.api_client import ApiClient
    from dx_pipelines.warehouse import get_warehouse

    s = settings or get_settings()
    wh = warehouse or get_warehouse(None, s, job="fx_daily")
    ctx = SyncContext(warehouse=wh, raw_dataset=DATASET, run_id=f"fx-{now_utc():%Y%m%d}", now=now_utc())
    try:
        out = sync_fx(ctx, s, http)
    except SourceError as exc:
        (api or ApiClient()).publish(
            "sync.failed", None, {"source": "fx_vcb", "reason": exc.reason, "detail": exc.detail[:300]}, "s1-ingest"
        )
        return {"status": "failed", "reason": exc.reason}
    return {"status": "success", "rows": out.rows_loaded}
