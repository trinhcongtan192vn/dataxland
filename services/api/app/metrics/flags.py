"""Cờ cần chú ý (FR-AGY-01, spec 03 §7). Ngưỡng lấy từ `attention` trong cấu hình khách.

| Mã | Quy tắc | Phạm vi |
|---|---|---|
| `OVERSPEND` | `budget_pacing > 1 + overspend_pct/100` trong tháng hiện tại | Theo nền tảng |
| `ROAS_DROP` | `roas_blended` 7 ngày gần nhất thấp hơn trung bình 4 tuần trước đó quá `roas_drop_pct` | Theo khách |
| `PLATFORM_OVERCLAIM` | `roas_platform` của nền tảng lớn hơn `roas_blended` của khách quá `platform_gap_pct` | Theo nền tảng, 7 ngày |
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.auth.context import AuthContext
from app.metrics.engine import QueryIn, query
from app.metrics.periods import resolve
from dx_common.timeutil import month_end, month_start, today_vn


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%".replace(".", ",")


def compute_flags(ctx: AuthContext, *, db: Session | None = None, today: date | None = None) -> list[dict[str, Any]]:
    att = ctx.tenant.attention
    out: list[dict[str, Any]] = []
    t = today or today_vn()
    y = resolve({"preset": "yesterday"}, t).end
    if ctx.tenant.pack == "agency" or ctx.tenant.ad_platforms():
        # OVERSPEND – theo nền tảng, tháng hiện tại
        if ctx.tenant.pack == "agency":
            res = query(
                ctx,
                QueryIn(
                    metrics=["budget_pacing"],
                    dimensions=["platform"],
                    time={"from": month_start(y).isoformat(), "to": month_end(y).isoformat()},
                ),
                db=db,
                caller="flags",
                today=t,
                allow_hidden=True,
            )
            limit = 1 + att.overspend_pct / 100
            for r in res["rows"]:
                v = r.get("budget_pacing")
                if v is not None and v > limit:
                    out.append(
                        {
                            "code": "OVERSPEND",
                            "platform": r["platform"],
                            "value": v,
                            "threshold": limit,
                            "message_vi": f"{r['platform']}: chi nhanh hơn tiến độ ngân sách {_pct(v - 1)} (ngưỡng {_pct(limit - 1)})",
                        }
                    )
        # ROAS_DROP – theo khách
        res = query(
            ctx,
            QueryIn(metrics=["roas_blended"], time={"preset": "last_7_days"}, compare="trailing_4_weeks"),
            db=db,
            caller="flags",
            today=t,
            allow_hidden=True,
        )
        if res["rows"]:
            cur = res["rows"][0].get("roas_blended")
            base = (res["rows"][0].get("compare") or {}).get("roas_blended")
            if cur is not None and base:
                drop = (base - cur) / base
                if drop > att.roas_drop_pct / 100:
                    out.append(
                        {
                            "code": "ROAS_DROP",
                            "value": round(cur, 4),
                            "baseline": round(base, 4),
                            "threshold": att.roas_drop_pct / 100,
                            "message_vi": f"ROAS thật 7 ngày giảm {_pct(drop)} so với trung bình 4 tuần trước",
                        }
                    )
            blended = cur
        else:
            blended = None
        # PLATFORM_OVERCLAIM – theo nền tảng, 7 ngày
        if blended and ctx.tenant.pack == "agency":
            res = query(
                ctx,
                QueryIn(metrics=["roas_platform"], dimensions=["platform"], time={"preset": "last_7_days"}),
                db=db,
                caller="flags",
                today=t,
                allow_hidden=True,
            )
            limit = blended * (1 + att.platform_gap_pct / 100)
            for r in res["rows"]:
                v = r.get("roas_platform")
                if v is not None and v > limit:
                    out.append(
                        {
                            "code": "PLATFORM_OVERCLAIM",
                            "platform": r["platform"],
                            "value": round(v, 4),
                            "threshold": round(limit, 4),
                            "message_vi": f"{r['platform']}: ROAS nền tảng {v:.1f}x cao hơn ROAS thật {blended:.1f}x quá {att.platform_gap_pct:.0f}%".replace(
                                ".", ","
                            ),
                        }
                    )
    return out
