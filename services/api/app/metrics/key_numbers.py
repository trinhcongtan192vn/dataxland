"""Ba số chính – nơi duy nhất định nghĩa (spec 03 §5). Báo cáo tuần, Telegram bot (`/week`, `/month`) và cổng đều
gọi qua `GET /v1/metrics/key-numbers?period=...`.

| Gói | Số 1 | Số 2 | Số 3 |
|---|---|---|---|
| seller | `net_revenue` | `net_profit_after_fees` | % thay đổi `net_profit_after_fees` so với kỳ trước |
| agency | `ad_spend` | `roas_blended` | `budget_pacing` của tháng chứa ngày cuối kỳ |
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.auth.context import AuthContext
from app.errors import ApiError
from app.metrics.engine import QueryIn, query
from app.metrics.periods import previous_period, resolve
from app.metrics.registry import get_registry
from dx_common.timeutil import month_end, month_start

PERIODS = ("this_week", "last_week", "this_month", "last_month")
# Kỳ so sánh của số 3 (spec 06 §4.5, spec 08 §4).
PERIOD_LABEL_VI = {
    "this_week": "cùng kỳ tuần trước",
    "last_week": "tuần trước",
    "this_month": "cùng kỳ tháng trước",
    "last_month": "tháng trước",
}
KEY_METRICS = {
    "seller": ["net_revenue", "net_profit_after_fees"],
    "agency": ["ad_spend", "roas_blended", "budget_pacing"],
}


def _change(cur: float | int | None, prev: float | int | None) -> float | None:
    if cur is None or prev is None or prev == 0:
        return None
    return round((float(cur) - float(prev)) / abs(float(prev)), 6)


def key_numbers(
    ctx: AuthContext, period: str, *, db: Session | None = None, today: date | None = None, caller: str = "key_numbers"
) -> dict[str, Any]:
    if period not in PERIODS:
        raise ApiError(400, "PERIOD_INVALID", f"period phải là một trong {', '.join(PERIODS)}")
    reg = get_registry()
    p = resolve({"preset": period}, today)
    # Ba số chính là số tổng hợp dùng chung; quyền xem từng chỉ số vẫn áp ở bộ máy (spec 03 §4.4).
    numbers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    as_of: str | None = None
    if ctx.pack == "seller":
        res = query(
            ctx,
            QueryIn(
                metrics=["net_revenue", "net_profit_after_fees"], time={"preset": period}, compare="previous_period"
            ),
            db=db,
            caller=caller,
            today=today,
        )
        row = res["rows"][0] if res["rows"] else {"compare": {}}
        cmp = row.get("compare") or {}
        rev, prof = row.get("net_revenue"), row.get("net_profit_after_fees")
        prev_prof = cmp.get("net_profit_after_fees")
        meta = res["metrics"]
        numbers.append(
            {
                "key": "net_revenue",
                "metric": "net_revenue",
                "label_vi": meta["net_revenue"]["name_vi"],
                "value": rev if rev is not None else 0,
                "unit": "VND",
                "version": meta["net_revenue"]["version"],
                "change_pct": _change(rev, cmp.get("net_revenue")),
            }
        )
        numbers.append(
            {
                "key": "net_profit_after_fees",
                "metric": "net_profit_after_fees",
                "label_vi": meta["net_profit_after_fees"]["name_vi"],
                "value": prof if prof is not None else 0,
                "unit": "VND",
                "version": meta["net_profit_after_fees"]["version"],
                "change_pct": _change(prof, prev_prof),
            }
        )
        third: dict[str, Any] = {
            "key": "net_profit_change_pct",
            "metric": "net_profit_after_fees",
            "label_vi": f"Lãi so với {PERIOD_LABEL_VI[period]}",
            "unit": "percent",
            "version": meta["net_profit_after_fees"]["version"],
        }
        if prev_prof is None or prev_prof <= 0:
            third.update(value=None, note_vi="Kỳ trước không có lãi để so sánh")
        else:
            third["value"] = _change(prof, prev_prof)
        numbers.append(third)
        warnings, as_of = res["warnings"], res["data_as_of"]
    else:
        res = query(
            ctx,
            QueryIn(metrics=["ad_spend", "roas_blended"], time={"preset": period}, compare="previous_period"),
            db=db,
            caller=caller,
            today=today,
        )
        row = res["rows"][0] if res["rows"] else {"compare": {}}
        cmp = row.get("compare") or {}
        meta = res["metrics"]
        numbers.append(
            {
                "key": "ad_spend",
                "metric": "ad_spend",
                "label_vi": meta["ad_spend"]["name_vi"],
                "value": row.get("ad_spend") or 0,
                "unit": "VND",
                "version": meta["ad_spend"]["version"],
                "change_pct": _change(row.get("ad_spend"), cmp.get("ad_spend")),
            }
        )
        numbers.append(
            {
                "key": "roas_blended",
                "metric": "roas_blended",
                "label_vi": meta["roas_blended"]["name_vi"],
                "value": row.get("roas_blended"),
                "unit": "ratio",
                "version": meta["roas_blended"]["version"],
                "change_pct": _change(row.get("roas_blended"), cmp.get("roas_blended")),
            }
        )
        ms, me = month_start(p.end), month_end(p.end)
        bp = query(
            ctx,
            QueryIn(metrics=["budget_pacing"], time={"from": ms.isoformat(), "to": me.isoformat()}),
            db=db,
            caller=caller,
            today=today,
        )
        pacing = bp["rows"][0].get("budget_pacing") if bp["rows"] else None
        bpm = reg.get("budget_pacing")
        numbers.append(
            {
                "key": "budget_pacing",
                "metric": "budget_pacing",
                "label_vi": bpm.name_vi if bpm else "Tiến độ ngân sách",
                "value": pacing,
                "unit": "ratio",
                "version": bpm.version if bpm else "1.0.0",
                "month": ms.strftime("%Y-%m"),
            }
        )
        warnings, as_of = res["warnings"], res["data_as_of"]
    prev = previous_period(p)
    return {
        "pack": ctx.pack,
        "period": {"preset": period, "from": p.start.isoformat(), "to": p.end.isoformat()},
        "previous": {"from": prev.start.isoformat(), "to": prev.end.isoformat()},
        "numbers": numbers,
        "data_as_of": as_of,
        "warnings": warnings,
    }


def number_text(n: dict[str, Any], *, scope: list[str] | None = None) -> str:
    """Định dạng một số chính cho tin nhắn; ngoài phạm vi nhóm Telegram thì "—" (spec 08 §3.6)."""
    from app.notify.render import f_change, f_unit

    if scope is not None and n.get("metric") not in scope:
        return "— (ngoài phạm vi của nhóm)"
    if n.get("value") is None:
        return n.get("note_vi") or "—"
    text = f_change(n["value"]) if n["key"] == "net_profit_change_pct" else f_unit(n["value"], n["unit"])
    if n.get("change_pct") is not None and n["unit"] != "percent":
        text += f" ({f_change(n['change_pct'])})"
    return text


def as_decimal(v: Any) -> Decimal | None:
    return None if v is None else Decimal(str(v))
