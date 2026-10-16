"""Đổi khoảng thời gian định sẵn sang ngày cụ thể theo giờ Việt Nam (spec 03 §4.1).

- `this_week`: thứ Hai đến hôm qua; nếu hôm nay là thứ Hai thì là tuần trước (spec 08 §4).
- `this_month`: đầu tháng đến hôm qua; ngày 1 thì là tháng trước.
- `previous_period` của `this_week`, `this_month`: cùng số ngày tương ứng của tuần, tháng trước; kỳ khác: kỳ cùng
  độ dài ngay trước đó.
- `trailing_4_weeks`: 4 kỳ cùng độ dài ngay trước kỳ đang xét, lấy trung bình.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.errors import ApiError
from dx_common.timeutil import add_months, month_start, today_vn, week_start

PRESETS = (
    "today",
    "yesterday",
    "this_week",
    "last_week",
    "this_month",
    "last_month",
    "last_7_days",
    "last_30_days",
    "last_90_days",
)


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    preset: str | None = None

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def shift_days(self, n: int) -> Period:
        return Period(self.start - timedelta(days=n), self.end - timedelta(days=n))


def resolve(spec: dict[str, str] | None, today: date | None = None) -> Period:
    t = today or today_vn()
    y = t - timedelta(days=1)
    if not spec:
        spec = {"preset": "last_30_days"}
    if "preset" in spec:
        p = spec["preset"]
        if p == "today":
            return Period(t, t, p)
        if p == "yesterday":
            return Period(y, y, p)
        if p == "this_week":
            ws = week_start(y)
            return Period(ws, y, p)
        if p == "last_week":
            ws = week_start(t) - timedelta(days=7)
            return Period(ws, ws + timedelta(days=6), p)
        if p == "this_month":
            return Period(month_start(y), y, p)
        if p == "last_month":
            first = add_months(month_start(t), -1)
            return Period(first, month_start(t) - timedelta(days=1), p)
        if p in ("last_7_days", "last_30_days", "last_90_days"):
            n = int(p.split("_")[1])
            return Period(y - timedelta(days=n - 1), y, p)
        raise ApiError(400, "TIME_INVALID", f"preset không hợp lệ: {p}")
    try:
        start = date.fromisoformat(spec["from"])
        end = date.fromisoformat(spec["to"])
    except (KeyError, ValueError) as exc:
        raise ApiError(400, "TIME_INVALID", "time cần preset hoặc from, to dạng YYYY-MM-DD") from exc
    if end < start:
        raise ApiError(400, "TIME_INVALID", "from phải trước to")
    if (end - start).days > 800:
        raise ApiError(400, "TIME_INVALID", "khoảng thời gian tối đa khoảng 2 năm")
    return Period(start, end)


def previous_period(p: Period) -> Period:
    if p.preset == "this_week":
        return p.shift_days(7)
    if p.preset in ("this_month", "last_month"):
        ps = add_months(p.start, -1)
        if p.preset == "last_month":
            return Period(ps, p.start - timedelta(days=1))
        return Period(ps, min(add_months(p.end, -1), p.start - timedelta(days=1)))
    return p.shift_days(p.days)


def trailing_periods(p: Period, n: int = 4) -> list[Period]:
    """4 kỳ cùng độ dài ngay trước kỳ đang xét (theo bước tuần nếu kỳ ngắn hơn hoặc bằng 7 ngày)."""
    step = 7 if p.days <= 7 else p.days
    return [p.shift_days(step * (i + 1)) for i in range(n)]
