"""Dựng dữ liệu đầu vào của mẫu tin từ sự kiện (spec 04 §5.3). Không có trường thông tin người mua."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Tenant
from app.notify.types import Button
from dx_common.config import get_settings
from dx_common.events import Event
from dx_common.timeutil import iso_week

REASON_VI = {
    "auth_revoked": "Quyền truy cập API của sàn bị thu hồi hoặc token không làm mới được",
    "rate_limited": "Nền tảng giới hạn tần suất gọi API",
    "api_error": "API của nguồn trả lỗi",
    "windsor_stale": "Dữ liệu Windsor quá hạn độ tươi",
    "override_invalid": "File ghi đè ánh xạ trạng thái không hợp lệ",
    "dbt_error": "dbt build lỗi khi chạy",
    "swap_failed": "Không hoán đổi được bảng marts",
    "cube_refresh_failed": "Không làm mới được Cube",
}

HC_STATUS_VI = {
    "healthcheck.submitted": "Email đã xác nhận, bắt đầu xử lý file",
    "healthcheck.completed": "Đã dựng kết quả, chờ duyệt",
    "healthcheck.failed": "Không xử lý được file nào, cần kiểm tra",
}


@dataclass
class Plan:
    """Một loại tin cho một nhóm người nhận."""

    audience: str  # "team" | "customer"
    template: str
    data: dict[str, Any]
    buttons: list[Button] = field(default_factory=list)
    group_reason: str | None = None  # gộp cảnh báo team theo (tenant_id, type, reason)
    metrics: tuple[str, ...] = ()  # chỉ số có trong tin, để kiểm phạm vi nhóm Telegram


def _base() -> str:
    return get_settings().dx_public_base_url.rstrip("/")


def tenant_label(db: Session, tenant_id: str | None) -> str:
    if not tenant_id:
        return "Toàn hệ thống"
    t = db.get(Tenant, tenant_id)
    return f"{t.name} ({tenant_id})" if t else tenant_id


def tenant_name(db: Session, tenant_id: str) -> str:
    t = db.get(Tenant, tenant_id)
    return t.name if t else tenant_id


def build(db: Session, ev: Event) -> list[Plan]:
    t = ev.type
    p = ev.payload
    base = _base()
    ops_url = f"{base}/ops/tenants/{ev.tenant_id}" if ev.tenant_id else f"{base}/ops"
    if t == "sync.failed":
        return [
            Plan(
                "team",
                "sync_failed",
                {
                    "tenant_label": tenant_label(db, ev.tenant_id),
                    "source": p.get("source"),
                    "reason": p["reason"],
                    "reason_vi": REASON_VI.get(p["reason"], p["reason"]),
                    "detail": (p.get("detail") or "")[:500],
                    "run_id": p.get("run_id"),
                    "ops_url": ops_url,
                },
                [Button("Mở màn hình vận hành", ops_url)],
                group_reason=f"{p['reason']}:{p.get('source') or ''}",
            )
        ]
    if t == "test.failed":
        failures = p.get("failures", [])
        return [
            Plan(
                "team",
                "test_failed",
                {
                    "tenant_label": tenant_label(db, ev.tenant_id),
                    "failures": failures,
                    "run_id": p.get("run_id"),
                    "ops_url": ops_url,
                },
                [Button("Xem lỗi chặn", ops_url)],
                group_reason=",".join(sorted(f["test"] for f in failures))[:200],
            )
        ]
    if t == "metric.anomaly":
        from app.metrics.registry import get_registry

        m = get_registry().get(p["metric"])
        data = {
            "tenant_name": tenant_name(db, ev.tenant_id or ""),
            "metric_name": m.name_vi if m else p["metric"],
            "unit": m.unit if m else "count",
            "value": p.get("value"),
            "baseline": p.get("baseline"),
            "diff_pct": p["diff_pct"],
            "direction": p["direction"],
            "period_label": _period_label(p),
            "dashboard_url": f"{base}/app/dashboards/{_pack(db, ev.tenant_id)}?t={ev.tenant_id}",
        }
        buttons = [Button("Mở dashboard", data["dashboard_url"])]
        plans = [Plan("team", "anomaly", data, buttons, group_reason=p["metric"])]
        cfg = _config(db, ev.tenant_id)
        if cfg is not None and cfg.notify.anomaly_alerts:
            plans.append(Plan("customer", "anomaly", data, buttons, metrics=(p["metric"],)))
        return plans
    if t == "report.ready":
        return []  # gửi theo từng người nhận, có open_token riêng (dispatcher._report_ready)
    if t == "decision.remeasure_due":
        from app.db.models import Decision
        from app.metrics.registry import get_registry

        d = db.get(Decision, p["decision_id"])
        if d is None:
            return []
        m = get_registry().get(d.metric)
        url = f"{base}/app/decisions/{d.id}?t={d.tenant_id}"
        return [
            Plan(
                "team",
                "decision_remeasure_due",
                {
                    "tenant_label": tenant_label(db, d.tenant_id),
                    "title": d.title,
                    "metric_name": m.name_vi if m else d.metric,
                    "remeasure_on": d.remeasure_on,
                    "url": url,
                },
                [Button("Mở quyết định", url)],
                group_reason=d.id,
            )
        ]
    if t in HC_STATUS_VI:
        url = f"{base}/ops/health-checks/{p['check_id']}"
        from app.db.models import HealthCheck

        hc = db.get(HealthCheck, p["check_id"])
        return [
            Plan(
                "team",
                "healthcheck_team",
                {
                    "check_id": p["check_id"],
                    "shop_name": hc.shop_name if hc else None,
                    "status_vi": HC_STATUS_VI[t],
                    "url": url,
                },
                [Button("Mở lượt kiểm tra", url)],
                group_reason=f"{t}:{p['check_id']}",
            )
        ]
    if t == "report.built":
        url = f"{base}/ops/reports/{p['report_id']}"
        from app.db.models import Report

        r = db.get(Report, p["report_id"])
        week = _week_label(r.period_start) if r else p.get("period", "")
        return [
            Plan(
                "team",
                "report_built",
                {
                    "tenant_label": tenant_label(db, ev.tenant_id),
                    "week_label": week,
                    "url": url,
                    "data_stale": bool(r.data_stale) if r else False,
                },
                [Button("Viết nhận định", url)],
                group_reason=p["report_id"],
            )
        ]
    if t in ("tenant.created", "tenant.bootstrap_required", "tenant.config_invalid"):
        kind_vi = {
            "tenant.created": "Đã tạo môi trường cho khách",
            "tenant.bootstrap_required": "Khách mới cần chạy bootstrap",
            "tenant.config_invalid": "File cấu hình khách lỗi",
        }[t]
        next_step = {
            "tenant.created": "Lần chạy đầu sẽ nạp dữ liệu lịch sử, chạy toàn bộ test và đối soát.",
            "tenant.bootstrap_required": f"Chạy: uv run python ops/bootstrap_tenant.py {ev.tenant_id}",
            "tenant.config_invalid": "Sửa file và mở pull request.",
        }[t]
        label = p.get("path") if t == "tenant.config_invalid" else tenant_label(db, ev.tenant_id)
        return [
            Plan(
                "team",
                "tenant_event",
                {
                    "kind_vi": kind_vi,
                    "tenant_label": label,
                    "errors": p.get("errors", []),
                    "next_step": next_step,
                },
                [Button("Mở vận hành", ops_url)],
                group_reason=f"{t}:{label}",
            )
        ]
    return []


def _config(db: Session, tenant_id: str | None) -> Any:
    from dx_common.tenants import TenantConfig

    if not tenant_id:
        return None
    t = db.get(Tenant, tenant_id)
    return TenantConfig.model_validate(t.config) if t else None


def _pack(db: Session, tenant_id: str | None) -> str:
    t = db.get(Tenant, tenant_id) if tenant_id else None
    return t.pack if t else "seller"


def _period_label(p: dict[str, Any]) -> str:
    period = str(p.get("period", ""))
    if p.get("grain") == "week" and len(period) >= 10:
        return _week_label(date.fromisoformat(period[:10]))
    try:
        return date.fromisoformat(period[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return period


def _week_label(start: date) -> str:
    from dx_common.timeutil import format_week_label

    return format_week_label(start)


def week_no(start: date) -> int:
    return iso_week(start)[1]
