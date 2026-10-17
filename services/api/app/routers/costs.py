"""Chi phí và giờ người theo khách (spec 04 §6, FR-OPS-06, NFR-08).

| Endpoint | Việc |
|---|---|
| `POST /v1/internal/costs` | Job `gcp_costs` ghi chi phí GCP theo nhãn `tenant_id` của một tháng (thay toàn bộ mục đó) |
| `GET /v1/ops/costs?month=` | Chi phí theo mục, tổng và giờ người của mỗi khách trong tháng |
| `POST /v1/ops/costs/allocate` | Chia hóa đơn Windsor hoặc Claude của tháng cho các khách |
| `PUT /v1/ops/tenants/{id}/hours` | Nhập giờ người của khách trong tháng |

Quy tắc chia (ADR 0002 #56): Windsor theo số nguồn Windsor đang bật của khách; Claude theo chi phí AI đã ghi nhận
từng khách trong tháng (hỏi đáp, agent), không có thì chia đều cho khách đang hoạt động.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.context import CurrentUser, get_current_user
from app.auth.internal import ServiceCaller, require_service
from app.db import get_db
from app.db.models import Tenant, TenantCost, TenantHours
from app.errors import ApiError
from app.routers.ops import require_staff
from dx_common.ids import new_ulid
from dx_common.tenants import TenantConfig
from dx_common.timeutil import month_start, now_utc, today_vn

router = APIRouter(tags=["costs"])

MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"
ITEMS = ("gcp", "windsor", "ai")


def _month(s: str) -> date:
    y, m = s.split("-")
    return date(int(y), int(m), 1)


def _active(db: Session) -> list[Tenant]:
    return list(db.scalars(select(Tenant).where(Tenant.status == "active").order_by(Tenant.tenant_id)))


def _replace(db: Session, month: date, item: str, amounts: dict[str, Decimal]) -> None:
    db.execute(delete(TenantCost).where(TenantCost.month == month, TenantCost.item == item))
    for tid, amt in amounts.items():
        db.add(TenantCost(id=new_ulid(), month=month, tenant_id=tid, item=item, amount_vnd=amt))


def split(total: Decimal, weights: dict[str, Decimal]) -> dict[str, Decimal]:
    """Chia theo trọng số, làm tròn đến đồng; phần dư chia cho phần lẻ lớn nhất để tổng đúng bằng hóa đơn."""
    w = {k: v for k, v in weights.items() if v > 0}
    if not w:
        return {}
    s = sum(w.values())
    raw = {k: total * v / s for k, v in w.items()}
    out = {k: v.quantize(Decimal("1"), rounding=ROUND_DOWN) for k, v in raw.items()}
    rest = int(total.quantize(Decimal("1")) - sum(out.values()))
    for k in sorted(raw, key=lambda k: raw[k] - out[k], reverse=True)[: max(rest, 0)]:
        out[k] += 1
    return out


# --------------------------------------------------------------------------- nội bộ


class CostRow(BaseModel):
    tenant_id: str
    amount_vnd: Decimal = Field(ge=0)


class CostsIn(BaseModel):
    month: str = Field(pattern=MONTH)
    item: Literal["gcp"]
    rows: list[CostRow]


@router.post("/v1/internal/costs", status_code=204)
def internal_costs(body: CostsIn, _: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)) -> None:
    known = {t.tenant_id for t in db.scalars(select(Tenant))}
    _replace(db, _month(body.month), body.item, {r.tenant_id: r.amount_vnd for r in body.rows if r.tenant_id in known})


# --------------------------------------------------------------------------- màn vận hành


class TenantCostOut(BaseModel):
    tenant_id: str
    name: str
    items: dict[str, int]
    total_vnd: int
    hours: float | None
    hours_note: str | None


@router.get("/v1/ops/costs", response_model=list[TenantCostOut])
def ops_costs(
    month: str | None = Query(default=None, pattern=MONTH),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TenantCostOut]:
    require_staff(user, "ops.read")
    m = _month(month) if month else month_start(today_vn())
    costs: dict[str, dict[str, int]] = {}
    for c in db.scalars(select(TenantCost).where(TenantCost.month == m)):
        costs.setdefault(c.tenant_id, {})[c.item] = int(c.amount_vnd)
    hours = {h.tenant_id: h for h in db.scalars(select(TenantHours).where(TenantHours.month == m))}
    out: list[TenantCostOut] = []
    for t in db.scalars(select(Tenant).where(Tenant.status != "archived").order_by(Tenant.tenant_id)):
        items = costs.get(t.tenant_id, {})
        h = hours.get(t.tenant_id)
        out.append(
            TenantCostOut(
                tenant_id=t.tenant_id,
                name=t.name,
                items=items,
                total_vnd=sum(items.values()),
                hours=float(h.hours) if h else None,
                hours_note=h.note if h else None,
            )
        )
    return out


class AllocateIn(BaseModel):
    month: str = Field(pattern=MONTH)
    item: Literal["windsor", "claude"]
    amount_vnd: Decimal = Field(ge=0, max_digits=18, decimal_places=2)


@router.post("/v1/ops/costs/allocate")
def allocate(
    body: AllocateIn, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict[str, Any]:
    require_staff(user, "ops.write")
    m = _month(body.month)
    tenants = _active(db)
    if body.item == "windsor":
        weights = {
            t.tenant_id: Decimal(
                sum(1 for s in TenantConfig.model_validate(t.config).enabled_sources() if s.connector == "windsor")
            )
            for t in tenants
        }
        item = "windsor"
    else:
        used = {
            c.tenant_id: Decimal(c.amount_vnd)
            for c in db.scalars(select(TenantCost).where(TenantCost.month == m, TenantCost.item == "ai"))
        }
        weights = used if any(v > 0 for v in used.values()) else {t.tenant_id: Decimal(1) for t in tenants}
        item = "ai"  # hóa đơn thật thay số ước tính từ token
    parts = split(body.amount_vnd, weights)
    if body.amount_vnd > 0 and not parts:
        raise ApiError(422, "NO_ALLOCATION_BASE", "Không có khách nào để chia hóa đơn này")
    _replace(db, m, item, parts)
    audit(
        db,
        action="costs.allocated",
        actor_user_id=user.id,
        target=f"{body.item}:{body.month}",
        detail={"amount_vnd": str(body.amount_vnd), "tenants": len(parts)},
    )
    return {"month": body.month, "item": item, "allocated": {k: int(v) for k, v in parts.items()}}


class HoursIn(BaseModel):
    month: str = Field(pattern=MONTH)
    hours: Decimal = Field(ge=0, max_digits=8, decimal_places=2)
    note: str | None = Field(default=None, max_length=500)


@router.put("/v1/ops/tenants/{tenant_id}/hours", status_code=204)
def put_hours(
    tenant_id: str, body: HoursIn, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    require_staff(user, "ops.write")
    if db.get(Tenant, tenant_id) is None:
        raise ApiError(404, "TENANT_NOT_FOUND", "Không tìm thấy khách")
    m = _month(body.month)
    stmt = insert(TenantHours).values(
        id=new_ulid(), month=m, tenant_id=tenant_id, hours=body.hours, note=body.note, created_by=user.id
    )
    db.execute(
        stmt.on_conflict_do_update(
            constraint="uq_tenant_hours",
            set_={"hours": body.hours, "note": body.note, "created_by": user.id, "updated_at": now_utc()},
        )
    )
    audit(db, action="costs.hours_set", tenant_id=tenant_id, actor_user_id=user.id, detail={"month": body.month})
