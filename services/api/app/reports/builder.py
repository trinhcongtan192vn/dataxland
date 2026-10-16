"""Dựng snapshot báo cáo tuần (spec 06 §4.2, §4.3, FR-REP-01..03, FR-REP-07).

Mọi số lấy qua bộ máy chỉ số với ngữ cảnh nội bộ của khách, cho tuần ISO trước (thứ Hai → Chủ nhật). Snapshot ghi
đủ số, `version` của từng chỉ số, `data_as_of`, `run_id`, cảnh báo dữ liệu; báo cáo về sau chỉ hiển thị từ snapshot.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.auth.context import AuthContext
from app.metrics.engine import QueryIn, query
from app.metrics.flags import compute_flags
from app.metrics.key_numbers import key_numbers
from dx_common.timeutil import month_end, month_start, today_vn, week_start

TEMPLATE_VERSION = "1.0.0"
SELLER_PNL = [
    "net_revenue",
    "cogs",
    "platform_fees",
    "payment_fees",
    "shipping_cost",
    "return_cost",
    "allocated_ad_spend",
    "other_costs",
    "contribution_margin",
    "net_profit_after_fees",
    "net_margin_pct",
]


def last_week(today: date | None = None) -> tuple[date, date]:
    start = week_start(today or today_vn()) - timedelta(days=7)
    return start, start + timedelta(days=6)


class _Collector:
    """Gọi bộ máy chỉ số và gom metadata chỉ số, cảnh báo, `data_as_of` cho snapshot."""

    def __init__(self, ctx: AuthContext, db: Session, today: date) -> None:
        self.ctx, self.db, self.today = ctx, db, today
        self.metrics: dict[str, dict[str, Any]] = {}
        self.warnings: dict[str, dict[str, Any]] = {}
        self.data_as_of: str | None = None

    def q(self, **kw: Any) -> list[dict[str, Any]]:
        res = query(self.ctx, QueryIn(**kw), db=self.db, caller="report", today=self.today)
        self.metrics.update(res["metrics"])
        for w in res["warnings"]:
            self.warnings.setdefault(w["code"], w)
        self.data_as_of = self.data_as_of or res["data_as_of"]
        return list(res["rows"])


def _period(start: date, end: date) -> dict[str, str]:
    return {"from": start.isoformat(), "to": end.isoformat()}


def build_snapshot(
    ctx: AuthContext, db: Session, start: date, end: date, *, run_id: str | None, today: date | None = None
) -> dict[str, Any]:
    t = today or end + timedelta(days=1)
    c = _Collector(ctx, db, t)
    kn = key_numbers(ctx, "last_week", db=db, today=t, caller="report")
    for n in kn["numbers"]:
        c.metrics.setdefault(n["metric"], {"name_vi": n["label_vi"], "version": n["version"], "unit": n["unit"]})
    for w in kn["warnings"]:
        c.warnings.setdefault(w["code"], w)
    c.data_as_of = kn["data_as_of"]
    snap: dict[str, Any] = {
        "pack": ctx.pack,
        "period": _period(start, end),
        "previous": kn["previous"],
        "key_numbers": kn,
    }
    time = _period(start, end)
    if ctx.pack == "seller":
        # Tối đa 10 chỉ số mỗi truy vấn: chia hai lần rồi ghép một dòng.
        pnl: dict[str, Any] = {"compare": {}}
        for part in (SELLER_PNL[:6], SELLER_PNL[6:]):
            rows = c.q(metrics=part, time=time, compare="previous_period")
            if rows:
                pnl.update({k: v for k, v in rows[0].items() if k != "compare"})
                pnl["compare"].update(rows[0].get("compare") or {})
        snap["pnl"] = pnl
        dims = ["product", "product_name", "sku"]
        sku_metrics = ["sku_profit", "net_revenue", "order_count"]
        snap["top_skus"] = c.q(
            metrics=sku_metrics, dimensions=dims, time=time, order=[{"metric": "sku_profit", "dir": "desc"}], limit=5
        )
        snap["bottom_skus"] = c.q(
            metrics=sku_metrics, dimensions=dims, time=time, order=[{"metric": "sku_profit", "dir": "asc"}], limit=5
        )
        rates = c.q(metrics=["return_rate", "cancel_rate"], time=time, compare="previous_period")
        snap["rates"] = rates[0] if rates else {}
    else:
        snap["spend_by_platform"] = c.q(
            metrics=["ad_spend"], dimensions=["platform"], time=time, compare="previous_period"
        )
        ms, me = month_start(end), month_end(end)
        snap["budget"] = {
            "month": ms.strftime("%Y-%m"),
            "rows": c.q(
                metrics=["budget", "spend_mtd", "budget_used_pct", "budget_pacing"],
                dimensions=["platform"],
                time=_period(ms, me),
            ),
        }
        snap["roas"] = {
            "platforms": c.q(metrics=["roas_platform"], dimensions=["platform"], time=time),
            "blended": (c.q(metrics=["roas_blended"], time=time) or [{}])[0].get("roas_blended"),
        }
        if ctx.tenant.has_amazon():
            row = (c.q(metrics=["tacos"], time=time) or [{}])[0]
            acos = c.q(
                metrics=["acos"], time=time, filters=[{"dimension": "platform", "op": "eq", "value": "amazon_ads"}]
            )
            snap["amazon"] = {"acos": (acos or [{}])[0].get("acos"), "tacos": row.get("tacos")}
        snap["flags"] = compute_flags(ctx, db=db, today=t)
        snap["campaigns_attention"] = _campaigns_attention(c, ctx, time)
    snap["metrics"] = c.metrics
    snap["warnings"] = list(c.warnings.values())
    snap["data_as_of"] = c.data_as_of
    snap["run_id"] = run_id
    return snap


def _campaigns_attention(c: _Collector, ctx: AuthContext, time: dict[str, str]) -> list[dict[str, Any]]:
    """10 chiến dịch chi nhiều nhất tuần có `roas_platform` giảm quá `roas_drop_pct` so với TB 4 tuần trước."""
    rows = c.q(
        metrics=["ad_spend", "roas_platform"],
        dimensions=["platform", "campaign", "campaign_name"],
        time=time,
        compare="trailing_4_weeks",
        order=[{"metric": "ad_spend", "dir": "desc"}],
        limit=10,
    )
    limit = ctx.tenant.attention.roas_drop_pct / 100
    out: list[dict[str, Any]] = []
    for r in rows:
        cur = r.get("roas_platform")
        base = (r.get("compare") or {}).get("roas_platform")
        if cur is None or not base:
            continue
        drop = (base - cur) / base
        if drop > limit:
            out.append(
                {
                    "platform": r.get("platform"),
                    "campaign": r.get("campaign"),
                    "campaign_name": r.get("campaign_name"),
                    "ad_spend": r.get("ad_spend"),
                    "roas_platform": cur,
                    "baseline": base,
                    "drop_pct": round(drop, 4),
                }
            )
    return out
