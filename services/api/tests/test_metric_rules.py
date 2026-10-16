"""Phát hiện bất thường và cờ cần chú ý (spec 03 §7, §8, §11): FR-MET-07, FR-AGY-01."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import REPO

TODAY = date(2026, 10, 16)


def _ctx(tenant: str, **attention: float) -> Any:
    from app.auth.context import AuthContext
    from dx_common.tenants import load_tenant_file

    cfg = load_tenant_file(Path(REPO / "tenants" / f"{tenant}.yml"))
    if attention:
        cfg = cfg.model_copy(update={"attention": cfg.attention.model_copy(update=attention)})
    return AuthContext(
        tenant_id=tenant,
        role="internal",
        pack=cfg.pack,
        dataset_prefix=cfg.dataset_prefix,
        tenant=cfg,
        caller="internal",
    )


def test_fr_met_07_anomaly_40pct(session: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from sqlalchemy import func, select

    from app.db.models import MetricAnomaly
    from app.metrics import anomaly

    # Kỳ gần nhất (hôm qua cho grain day, tuần trước cho grain week) cao hơn 40% so với 4 kỳ trước.
    current_starts = {date(2026, 10, 15), date(2026, 10, 5)}

    def fake_value(ctx: Any, metric: str, start: date, end: date, db: Any) -> Decimal:
        return Decimal(140) if start in current_starts else Decimal(100)

    monkeypatch.setattr(anomaly, "_value", fake_value)
    ctx = _ctx("demo_seller")
    events = anomaly.detect(ctx, session, today=TODAY)
    assert events, "phải có ít nhất một bất thường"
    assert {e["metric"] for e in events} >= {"net_revenue", "net_profit_after_fees"}
    assert all(e["diff_pct"] == pytest.approx(0.4) for e in events)
    rev = next(e for e in events if e["metric"] == "net_revenue")
    assert rev["direction"] == "good"
    session.flush()
    n = session.scalar(select(func.count()).select_from(MetricAnomaly).where(MetricAnomaly.tenant_id == "demo_seller"))
    assert n == len(events)
    # Chạy lại cùng kỳ: không phát lại.
    assert anomaly.detect(ctx, session, today=TODAY) == []


def test_fr_met_07_below_threshold_silent(session: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.metrics import anomaly

    monkeypatch.setattr(anomaly, "_value", lambda ctx, metric, start, end, db: Decimal(100))
    assert anomaly.detect(_ctx("demo_seller"), session, today=TODAY) == []


def _fake_query(pacing: dict[str, float], roas: float, roas_base: float, platform: dict[str, float]) -> Any:
    def q(ctx: Any, body: Any, **_: Any) -> dict[str, Any]:
        m = body.metrics[0]
        if m == "budget_pacing":
            rows = [{"platform": p, "budget_pacing": v} for p, v in pacing.items()]
        elif m == "roas_blended":
            rows = [{"roas_blended": roas, "compare": {"roas_blended": roas_base}}]
        else:
            rows = [{"platform": p, "roas_platform": v} for p, v in platform.items()]
        return {"rows": rows, "warnings": [], "data_as_of": None}

    return q


@pytest.mark.parametrize(
    ("attention", "expect"),
    [
        # Mặc định: vượt 15%, giảm 25%, chênh 50%.
        ({}, {"OVERSPEND:meta_ads", "ROAS_DROP", "PLATFORM_OVERCLAIM:meta_ads"}),
        # Ghi đè nới ngưỡng: không cờ nào bật.
        ({"overspend_pct": 30.0, "roas_drop_pct": 40.0, "platform_gap_pct": 80.0}, set()),
        # Ghi đè siết ngưỡng: thêm google_ads.
        (
            {"overspend_pct": 5.0, "roas_drop_pct": 10.0, "platform_gap_pct": 20.0},
            {
                "OVERSPEND:meta_ads",
                "OVERSPEND:google_ads",
                "ROAS_DROP",
                "PLATFORM_OVERCLAIM:meta_ads",
                "PLATFORM_OVERCLAIM:google_ads",
            },
        ),
    ],
)
def test_flags_defaults_and_override(
    monkeypatch: pytest.MonkeyPatch, attention: dict[str, float], expect: set[str]
) -> None:
    from app.metrics import flags

    # pacing meta 1.2, google 1.1; ROAS 2.1 so với 3.0 (giảm 30%); ROAS nền tảng meta 3.3 (+57%), google 2.6 (+24%).
    monkeypatch.setattr(
        flags,
        "query",
        _fake_query({"meta_ads": 1.2, "google_ads": 1.1}, 2.1, 3.0, {"meta_ads": 3.3, "google_ads": 2.6}),
    )
    out = flags.compute_flags(_ctx("demo_agency", **attention), today=TODAY)
    got = {f"{f['code']}:{f['platform']}" if "platform" in f else f["code"] for f in out}
    assert got == expect
    for f in out:
        assert f["message_vi"]
