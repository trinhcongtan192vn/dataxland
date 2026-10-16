"""FR-ING-06, FR-REP-01 (lịch), spec 04 §3.3, §3.5."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from dx_common.events import Event
from dx_pipelines.schedule import due_runs, sync_interval, weekly_to_cron
from dx_pipelines.sensors.events import plan_runs


def _tenant(sync: str, weekly: str = "MON 07:00", status: str = "active") -> dict[str, Any]:
    return {
        "tenant_id": "demo_seller",
        "status": status,
        "config": {"schedule": {"sync": sync, "weekly_report": weekly}},
    }


def test_fr_ing_06_schedule_from_config() -> None:
    # 2026-10-16 04:59:30 UTC = 11:59:30 giờ Việt Nam.
    last = datetime(2026, 10, 16, 4, 59, 30, tzinfo=UTC)
    now = last + timedelta(minutes=1)
    runs = due_runs([_tenant("0 */6 * * *")], last, now)
    assert [(r.job, r.due_at.strftime("%H:%M")) for r in runs] == [("tenant_pipeline", "12:00")]
    assert runs[0].run_key == "demo_seller:tenant_pipeline:2026-10-16T12:00"
    # Đổi cron trong cấu hình: lần đánh giá kế tiếp dùng cron mới, không sửa code.
    assert due_runs([_tenant("0 */6 * * *")], now, now + timedelta(minutes=60)) == []
    runs = due_runs([_tenant("30 12 * * *")], now, now + timedelta(minutes=60))
    assert [r.due_at.strftime("%H:%M") for r in runs] == ["12:30"]
    # Khách tạm dừng không chạy.
    assert due_runs([_tenant("* * * * *", status="paused")], last, now) == []


def test_weekly_report_due_monday_7am_vn() -> None:
    assert weekly_to_cron("MON 07:00") == "0 7 * * 1"
    last = datetime(2026, 10, 19, 0, 0, tzinfo=UTC)  # thứ Hai 07:00 VN = 00:00 UTC
    runs = due_runs([_tenant("0 0 1 1 *")], last - timedelta(minutes=1), last)
    assert [(r.job, r.due_at.strftime("%a %H:%M")) for r in runs] == [("weekly_report", "Mon 07:00")]
    assert sync_interval("0 */6 * * *", last) == timedelta(hours=6)


def _ev(i: int, type: str, tenant: str | None, at: datetime, payload: dict[str, Any] | None = None) -> Event:
    return Event(f"E{i:03d}", type, 1, tenant, at, "x", payload or {})


def test_inputs_changed_debounced_10_minutes() -> None:
    t0 = datetime(2026, 10, 16, 3, 0, tzinfo=UTC)
    runs, pending = plan_runs([_ev(1, "inputs.changed", "demo_seller", t0, {"kind": "product_costs"})], {}, t0)
    assert runs == [] and "demo_seller" in pending
    runs, pending = plan_runs(
        [_ev(2, "inputs.changed", "demo_seller", t0 + timedelta(minutes=5), {"kind": "ad_budgets"})],
        pending,
        t0 + timedelta(minutes=9),
    )
    assert runs == []
    runs, pending = plan_runs([], pending, t0 + timedelta(minutes=16))
    assert [r["tenant_id"] for r in runs] == ["demo_seller"] and pending == {}


def test_events_open_history_and_healthcheck_runs() -> None:
    t0 = datetime(2026, 10, 16, 3, 0, tzinfo=UTC)
    runs, _ = plan_runs(
        [
            _ev(1, "tenant.created", "acme01", t0),
            _ev(2, "healthcheck.submitted", None, t0, {"check_id": "01jb8x"}),
            _ev(3, "pipeline.requested", "demo_seller", t0, {"full_refresh": True}),
        ],
        {},
        t0,
    )
    assert runs[0]["config"] == {"history": True}
    assert runs[1] == {"job": "healthcheck", "check_id": "01jb8x", "key": "hc:E002"}
    assert runs[2]["config"] == {"full_refresh": True}


def test_definitions_load() -> None:
    from dx_pipelines.definitions import defs

    names = {j.name for j in defs.resolve_all_job_defs()}
    assert {
        "tenant_pipeline",
        "weekly_report",
        "healthcheck",
        "fx_daily",
        "sync_tenants",
        "healthcheck_cleanup",
        "decision_reminders",
        "events_cleanup",
    } <= names
