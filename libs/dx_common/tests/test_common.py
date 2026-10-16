from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from dx_common.money import format_foreign, format_vnd, parse_vnd_text, round_vnd
from dx_common.tenants import TenantValidationError, load_tenant_file, validate_dir
from dx_common.timeutil import format_week_label, iso_week, week_start

REPO = Path(__file__).resolve().parents[3]


def test_format_vnd() -> None:
    assert format_vnd(1234567) == "1.234.567 ₫"
    assert format_vnd(Decimal("1234567.5")) == "1.234.568 ₫"
    assert format_vnd(-5000) == "−5.000 ₫"
    assert format_vnd(None) == "—"
    assert format_foreign("1234.561") == "$1,234.56"
    assert round_vnd("0.4") == 0


@pytest.mark.parametrize(
    ("text", "value"),
    [("120000", 120000), ("120.000", 120000), ("120,000", 120000), ("1.250.000", 1250000), ("99.5", 99.5)],
)
def test_parse_vnd_text(text: str, value: float) -> None:
    assert parse_vnd_text(text) == Decimal(str(value))


@pytest.mark.parametrize("text", ["", "abc", "1.2,3"])
def test_parse_vnd_text_invalid(text: str) -> None:
    with pytest.raises(ValueError):
        parse_vnd_text(text)


def test_iso_week_vn() -> None:
    d = date(2026, 10, 8)
    assert week_start(d) == date(2026, 10, 5)
    assert iso_week(d) == (2026, 41)
    assert format_week_label(date(2026, 10, 5)) == "Tuần 41 (05/10–11/10)"


def test_demo_tenants_valid() -> None:
    ok, errs = validate_dir(REPO / "tenants")
    assert not errs, [str(e) for e in errs]
    assert {"demo_seller", "demo_agency"} <= set(ok)
    seller = ok["demo_seller"]
    assert seller.schedule.sync == "0 */6 * * *"
    assert seller.quality.freshness_hours == 8
    assert any(s.type == "portal" for s in seller.sources)
    assert ok["demo_agency"].schedule.sync == "0 */3 * * *"


def _write(tmp: Path, name: str, body: str) -> Path:
    p = tmp / f"{name}.yml"
    p.write_text(body, encoding="utf-8")
    return p


def test_tenant_rules(tmp_path: Path) -> None:
    p = _write(tmp_path, "bad_one", "tenant_id: other_name\nname: X\npack: seller\n")
    with pytest.raises(TenantValidationError, match="không trùng tên file"):
        load_tenant_file(p)

    p = _write(
        tmp_path,
        "acme01",
        "tenant_id: acme01\nname: A\npack: seller\nsources:\n  - type: shopee\n    connector: dlt\n"
        "    account_id: '1'\n    api_token: abc\n",
    )
    with pytest.raises(TenantValidationError) as exc:
        load_tenant_file(p)
    assert any("api_token" in m for m in exc.value.errors)

    p = _write(tmp_path, "acme02", "tenant_id: acme02\nname: A\npack: agency\n")
    with pytest.raises(TenantValidationError, match="quảng cáo"):
        load_tenant_file(p)

    p = _write(
        tmp_path,
        "acme03",
        "tenant_id: acme03\nname: A\npack: seller\nquality:\n  reconcile_tolerance_pct: 2.5\n",
    )
    cfg = load_tenant_file(p)
    assert cfg.quality.reconcile_tolerance_pct == {"default": 2.5}

    p = _write(tmp_path, "acme04", "tenant_id: acme04\nname: A\npack: seller\npartners: [nope]\n")
    with pytest.raises(TenantValidationError, match="partners"):
        load_tenant_file(p, partner_ids=set())
