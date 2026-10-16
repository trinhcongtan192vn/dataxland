"""Tỷ giá Vietcombank (spec 01 §6, FR-MOD-03)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import respx

from connectors.base import SyncContext
from connectors.fx_vcb.source import parse_vcb, run_fx_daily, sync_fx
from dx_common.config import Settings
from dx_pipelines.warehouse import DuckDBWarehouse

XML = (Path(__file__).parent / "fixtures" / "vcb.xml").read_text(encoding="utf-8")
URL = "https://vcb.test/pXML.aspx"


class FakeApi:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any, dict[str, Any]]] = []

    def publish(self, type: str, tenant_id: Any, payload: dict[str, Any], producer: str) -> str:
        from dx_common.events.schemas import payload_model

        payload_model(type).model_validate(payload)
        self.events.append((type, tenant_id, payload))
        return "e1"


def _settings() -> Settings:
    return Settings(fx_vcb_url=URL, fx_currencies="USD")


def test_parse_sell_rate() -> None:
    d, rates = parse_vcb(XML, ["USD"])
    assert d == date(2026, 10, 16)
    assert rates == {"USD": Decimal("26340.00")}


def test_fr_mod_03_fx_loaded_into_dx_ref(tmp_path: Path) -> None:
    wh = DuckDBWarehouse(tmp_path / "wh.duckdb")
    ctx = SyncContext(
        warehouse=wh,
        raw_dataset="dx_ref",
        run_id="fx",
        now=datetime(2026, 10, 16, 11, 30, tzinfo=UTC),
        extra={"dlt_dir": str(tmp_path / "dlt")},
    )
    with respx.mock() as m:
        m.get(URL).mock(return_value=httpx.Response(200, text=XML))
        sync_fx(ctx, _settings(), include_manual=False)
        sync_fx(ctx, _settings(), include_manual=False)  # chạy lại không nhân bản
    rows = wh.query(
        'select cast(date as varchar), currency, rate_vnd, source, _dx_record_hash from "dx_ref"."fx_rates"'
    )
    assert len(rows) == 1
    assert rows[0][:2] == ("2026-10-16", "USD") and Decimal(str(rows[0][2])) == Decimal("26340")
    assert rows[0][3] == "vcb" and rows[0][4]


def test_fx_failure_publishes_sync_failed(tmp_path: Path) -> None:
    api = FakeApi()
    wh = DuckDBWarehouse(tmp_path / "wh.duckdb")
    with respx.mock() as m:
        m.get(URL).mock(return_value=httpx.Response(503))
        res = run_fx_daily(_settings(), wh, api)
    assert res["status"] == "failed"
    assert api.events and api.events[0][0] == "sync.failed" and api.events[0][1] is None
    assert api.events[0][2]["source"] == "fx_vcb"
