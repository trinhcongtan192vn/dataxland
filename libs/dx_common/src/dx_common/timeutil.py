"""Chuyển giữa UTC và `Asia/Ho_Chi_Minh`; tuần ISO theo giờ Việt Nam (spec 00 §3.2).

`DX_TODAY` (YYYY-MM-DD) cố định "hôm nay" theo giờ Việt Nam. Chỉ dùng cho test và dữ liệu mẫu.
"""

from __future__ import annotations

import calendar
import os
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def now_utc() -> datetime:
    fake = os.environ.get("DX_NOW")
    if fake:
        return datetime.fromisoformat(fake.replace("Z", "+00:00")).astimezone(UTC)
    return datetime.now(UTC)


def to_vn(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(VN_TZ)


def today_vn() -> date:
    fake = os.environ.get("DX_TODAY")
    if fake:
        return date.fromisoformat(fake)
    return to_vn(now_utc()).date()


def iso_z(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC).isoformat().replace("+00:00", "Z")


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def iso_week(d: date) -> tuple[int, int]:
    y, w, _ = d.isocalendar()
    return y, w


def month_start(d: date) -> date:
    return d.replace(day=1)


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def days_in_month(d: date) -> int:
    return calendar.monthrange(d.year, d.month)[1]


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def format_date_vn(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def format_week_label(start: date) -> str:
    """ "Tuần 41 (06/10–12/10)" (spec 06 §2)."""
    end = start + timedelta(days=6)
    _, w = iso_week(start)
    return f"Tuần {w} ({start:%d/%m}–{end:%d/%m})"


def format_as_of(ts: datetime) -> str:
    """ "HH:mm dd/mm" theo giờ Việt Nam."""
    return to_vn(ts).strftime("%H:%M %d/%m")
