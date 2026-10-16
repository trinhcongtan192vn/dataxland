"""Tính lịch đến hạn từ cấu hình khách (FR-ING-06, FR-REP-01, spec 04 §3.3). Hàm thuần để test được."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from croniter import croniter  # type: ignore[import-untyped]

from dx_common.tenants.models import parse_weekly
from dx_common.timeutil import VN_TZ

MAX_CATCHUP = 3  # không mở hàng loạt lần chạy bù khi sensor dừng lâu


@dataclass(frozen=True)
class Due:
    tenant_id: str
    job: str  # tenant_pipeline | weekly_report
    due_at: datetime  # giờ Việt Nam

    @property
    def run_key(self) -> str:
        return f"{self.tenant_id}:{self.job}:{self.due_at.strftime('%Y-%m-%dT%H:%M')}"


def weekly_to_cron(expr: str) -> str:
    wd, h, m = parse_weekly(expr)
    return f"{m} {h} * * {(wd + 1) % 7}"


def _due_between(cron: str, start: datetime, end: datetime) -> list[datetime]:
    it = croniter(cron, start.astimezone(VN_TZ))
    out: list[datetime] = []
    while True:
        nxt: datetime = it.get_next(datetime)
        if nxt > end.astimezone(VN_TZ):
            break
        out.append(nxt)
    return out[-MAX_CATCHUP:]


def due_runs(tenants: list[dict[str, Any]], last_eval: datetime, now: datetime) -> list[Due]:
    """Mọi lần chạy đến hạn trong (last_eval, now]. Đổi cron trong cấu hình thì áp dụng ngay ở lần đánh giá kế tiếp."""
    out: list[Due] = []
    for t in tenants:
        if t.get("status") not in ("active", "trial"):
            continue
        cfg = t["config"]
        sched = cfg.get("schedule") or {}
        if sched.get("sync"):
            out += [Due(t["tenant_id"], "tenant_pipeline", d) for d in _due_between(sched["sync"], last_eval, now)]
        if sched.get("weekly_report"):
            cron = weekly_to_cron(sched["weekly_report"])
            out += [Due(t["tenant_id"], "weekly_report", d) for d in _due_between(cron, last_eval, now)]
    return out


def sync_interval(cron: str, at: datetime) -> timedelta:
    it = croniter(cron, at.astimezone(VN_TZ))
    a: datetime = it.get_prev(datetime)
    b: datetime = it.get_prev(datetime)
    return a - b
