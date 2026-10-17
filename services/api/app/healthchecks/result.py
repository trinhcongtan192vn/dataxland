"""Dựng `result` của lượt kiểm tra (spec 07 §6, FR-HC-03) bằng bộ máy chỉ số với ngữ cảnh nội bộ của lượt kiểm tra.

Không có SQL tính chỉ số ở đây (FR-HC-02): mọi số đi qua `query`. Kết quả là ảnh chụp, mọi số kèm `version`.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.context import internal_ctx
from app.db.models import HealthCheck, HealthCheckFile
from app.healthchecks.tenant import tenant_id_of
from app.metrics.engine import QueryIn, query

ORDER_KINDS = {"shopee_orders", "tiktok_shop_orders", "lazada_orders"}
AD_KINDS = {"meta_ads", "tiktok_ads", "google_ads"}
FEES = ["platform_fees", "payment_fees", "shipping_cost", "return_cost", "allocated_ad_spend"]


def file_period(db: Session, check_id: str) -> tuple[date, date] | None:
    files = list(
        db.scalars(
            select(HealthCheckFile).where(HealthCheckFile.check_id == check_id, HealthCheckFile.status == "loaded")
        )
    )
    orders = [f for f in files if f.declared_kind in ORDER_KINDS and f.date_from and f.date_to]
    use = orders or [f for f in files if f.date_from and f.date_to]
    if not use:
        return None
    return min(f.date_from for f in use if f.date_from), max(f.date_to for f in use if f.date_to)


class _Q:
    def __init__(self, ctx: Any, db: Session, time: dict[str, str]) -> None:
        self.ctx, self.db, self.time = ctx, db, time
        self.metrics: dict[str, Any] = {}
        self.as_of: str | None = None

    def __call__(self, metrics: list[str], **kw: Any) -> list[dict[str, Any]]:
        res = query(
            self.ctx,
            QueryIn(metrics=metrics, time=self.time, **kw),
            db=self.db,
            caller="healthcheck",
            allow_hidden=True,
        )
        self.metrics.update(res["metrics"])
        self.as_of = self.as_of or res["data_as_of"]
        return list(res["rows"])


def build_result(db: Session, hc: HealthCheck, mapping_issues: list[str] | None = None) -> dict[str, Any]:
    files = list(
        db.scalars(
            select(HealthCheckFile).where(HealthCheckFile.check_id == hc.check_id).order_by(HealthCheckFile.created_at)
        )
    )
    loaded = {f.declared_kind for f in files if f.status == "loaded"}
    period = file_period(db, hc.check_id)
    if period is None:
        return {"empty": True}
    ctx = internal_ctx(db, tenant_id_of(hc.check_id))
    q = _Q(ctx, db, {"from": period[0].isoformat(), "to": period[1].isoformat()})
    has_costs = "product_costs" in loaded
    has_orders = bool(loaded & ORDER_KINDS)
    out: dict[str, Any] = {
        "period": {"from": period[0].isoformat(), "to": period[1].isoformat()},
        "has_costs": has_costs,
        "has_ads": bool(loaded & AD_KINDS),
    }
    if has_orders:
        profit = "net_profit_after_fees" if has_costs else "contribution_margin"
        out["overview"] = {
            "profit_metric": profit,
            "values": (q(["gmv", "net_revenue", "order_count", profit]) or [{}])[0],
        }
        by_platform = q([*FEES, "net_revenue"], dimensions=["platform"])
        totals = (q([*FEES, "net_revenue"]) or [{}])[0]
        out["fees"] = {"by_platform": by_platform, "totals": totals}
        skus = q(
            ["sku_profit", "net_revenue", "order_count"],
            dimensions=["product", "product_name", "sku"],
            order=[{"metric": "sku_profit", "dir": "asc"}],
            limit=200,
        )
        out["loss_skus"] = {
            "before_cogs": not has_costs,
            "rows": [r for r in skus if (r.get("sku_profit") or 0) < 0][:20],
        }
        out["returns"] = {
            "by_platform": q(["return_rate", "return_cost"], dimensions=["platform"]),
            "by_product": q(
                ["return_cost", "return_rate"],
                dimensions=["product", "product_name", "sku"],
                order=[{"metric": "return_cost", "dir": "desc"}],
                limit=10,
            ),
        }
        # Đơn hoàn thành trong file đơn nhưng chưa có trong file quyết toán = đơn còn "tạm tính".
        unsettled = q(
            ["order_count", "net_revenue"],
            dimensions=["platform"],
            filters=[
                {"dimension": "order_status", "op": "eq", "value": "completed"},
                {"dimension": "is_provisional", "op": "eq", "value": True},
            ],
        )
        out["source_gaps"] = {"unsettled_completed": unsettled}
    if loaded & AD_KINDS:
        # Chỉ số quảng cáo thuộc gói Agency: đọc cùng dữ liệu của lượt kiểm tra với góc nhìn gói Agency.
        from dataclasses import replace

        actx = replace(ctx, pack="agency", tenant=ctx.tenant.model_copy(update={"pack": "agency"}))
        aq = _Q(actx, db, q.time)
        gap = (aq(["roas_blended", "platform_vs_actual_gap", "ad_spend"]) or [{}])[0] if has_orders else {}
        out.setdefault("source_gaps", {})["ads"] = {
            "by_platform": aq(["ad_spend", "roas_platform"], dimensions=["platform"]),
            **gap,
        }
        q.metrics.update(aq.metrics)
    out["file_quality"] = {
        "files": [
            {
                "id": f.id,
                "filename": f.filename,
                "declared_kind": f.declared_kind,
                "detected_kind": f.detected_kind,
                "status": f.status,
                "error_message_vi": f.error_message_vi,
                "date_from": f.date_from.isoformat() if f.date_from else None,
                "date_to": f.date_to.isoformat() if f.date_to else None,
                "rows_loaded": f.rows_loaded,
            }
            for f in files
        ],
        "mapping_issues": list(mapping_issues or []),
    }
    out["metrics"] = q.metrics
    out["data_as_of"] = q.as_of
    return out


def public_view(result: dict[str, Any] | None) -> dict[str, Any] | None:
    """Khách không thấy phần chất lượng file (spec 07 §6: chỉ hiện cho data lead)."""
    if result is None:
        return None
    return {k: v for k, v in result.items() if k != "file_quality"}
