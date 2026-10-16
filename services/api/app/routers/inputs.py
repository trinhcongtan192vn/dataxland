"""Giá vốn theo SKU và ngân sách quảng cáo (FR-INP-01..04, spec 05 §6.3–6.5).

Mỗi thay đổi phát `inputs.changed`; Dagster chạy lại pipeline sau 10 phút không có thay đổi mới (spec 04 §3.5).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.context import AuthContext, get_ctx
from app.auth.permissions import require
from app.db import get_db
from app.db.models import AdBudget, ProductCost, UploadJob
from app.errors import ApiError
from app.inputs.excel import FileRejected, build_template, parse_costs_file
from dx_common.events import publish
from dx_common.ids import new_ulid
from dx_common.timeutil import now_utc

router = APIRouter(prefix="/v1/inputs", tags=["inputs"])


def _changed(db: Session, ctx: AuthContext, kind: str) -> None:
    publish("inputs.changed", ctx.tenant_id, {"kind": kind}, "s6-portal", bind=db)


# --------------------------------------------------------------------------- giá vốn


class CostOut(BaseModel):
    id: str
    seller_sku: str
    unit_cost_vnd: int
    valid_from: date
    valid_to: date | None
    note: str | None
    updated_at: datetime


class CostIn(BaseModel):
    seller_sku: str = Field(min_length=1, max_length=200)
    unit_cost_vnd: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    valid_from: date
    note: str | None = Field(default=None, max_length=500)

    @field_validator("seller_sku")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("SKU trống")
        return v


class CostUpdate(BaseModel):
    unit_cost_vnd: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    note: str | None = Field(default=None, max_length=500)
    valid_from: date | None = None


def _active_costs(db: Session, tenant_id: str, sku: str | None = None) -> list[ProductCost]:
    q = select(ProductCost).where(ProductCost.tenant_id == tenant_id, ProductCost.deleted_at.is_(None))
    if sku:
        q = q.where(ProductCost.seller_sku == sku)
    return list(db.scalars(q.order_by(ProductCost.seller_sku, ProductCost.valid_from)))


def _with_valid_to(costs: list[ProductCost]) -> list[CostOut]:
    """`valid_to` = `valid_from` của bản kế tiếp trừ 1 ngày; bản cuối là null (spec 02 §4)."""
    out: list[CostOut] = []
    for i, c in enumerate(costs):
        nxt = costs[i + 1] if i + 1 < len(costs) and costs[i + 1].seller_sku == c.seller_sku else None
        out.append(
            CostOut(
                id=c.id,
                seller_sku=c.seller_sku,
                unit_cost_vnd=int(c.unit_cost_vnd.quantize(Decimal("1"))),
                valid_from=c.valid_from,
                valid_to=(nxt.valid_from - timedelta(days=1)) if nxt else None,
                note=c.note,
                updated_at=c.updated_at,
            )
        )
    return out


@router.get("/product-costs", response_model=list[CostOut])
def list_costs(
    sku: str | None = Query(default=None),
    active_on: date | None = Query(default=None),
    ctx: AuthContext = Depends(get_ctx),
    db: Session = Depends(get_db),
) -> list[CostOut]:
    require(ctx, "inputs.read", resource="product_costs")
    rows = _with_valid_to(_active_costs(db, ctx.tenant_id, sku))
    if active_on:
        rows = [r for r in rows if r.valid_from <= active_on and (r.valid_to is None or r.valid_to >= active_on)]
    return rows


def _upsert_cost(db: Session, ctx: AuthContext, sku: str, cost: Decimal, valid_from: date, note: str | None) -> str:
    existing = db.scalar(
        select(ProductCost).where(
            ProductCost.tenant_id == ctx.tenant_id,
            ProductCost.seller_sku == sku,
            ProductCost.valid_from == valid_from,
            ProductCost.deleted_at.is_(None),
        )
    )
    if existing is not None:
        existing.unit_cost_vnd = cost
        existing.note = note
        return existing.id
    pc = ProductCost(
        tenant_id=ctx.tenant_id,
        seller_sku=sku,
        unit_cost_vnd=cost,
        valid_from=valid_from,
        note=note,
        created_by=ctx.user_id,
    )
    db.add(pc)
    db.flush()
    return pc.id


@router.post("/product-costs", response_model=CostOut, status_code=201)
def create_cost(body: CostIn, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> CostOut:
    require(ctx, "inputs.write", resource="product_costs")
    cid = _upsert_cost(db, ctx, body.seller_sku, body.unit_cost_vnd, body.valid_from, body.note)
    audit(
        db,
        action="inputs.product_cost_set",
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        target=cid,
        detail={
            "seller_sku": body.seller_sku,
            "unit_cost_vnd": str(body.unit_cost_vnd),
            "valid_from": str(body.valid_from),
        },
    )
    _changed(db, ctx, "product_costs")
    db.flush()
    return next(r for r in _with_valid_to(_active_costs(db, ctx.tenant_id, body.seller_sku)) if r.id == cid)


@router.put("/product-costs/{cost_id}", response_model=CostOut)
def update_cost(
    cost_id: str, body: CostUpdate, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)
) -> CostOut:
    require(ctx, "inputs.write", resource="product_costs")
    pc = db.get(ProductCost, cost_id)
    if pc is None or pc.tenant_id != ctx.tenant_id or pc.deleted_at is not None:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy giá vốn")
    target_id = pc.id
    if body.valid_from is not None and body.valid_from != pc.valid_from:
        # Đổi `valid_from` thì tạo bản mới (spec 05 §6.3).
        target_id = _upsert_cost(
            db,
            ctx,
            pc.seller_sku,
            body.unit_cost_vnd if body.unit_cost_vnd is not None else pc.unit_cost_vnd,
            body.valid_from,
            body.note if body.note is not None else pc.note,
        )
    else:
        if body.unit_cost_vnd is not None:
            pc.unit_cost_vnd = body.unit_cost_vnd
        if body.note is not None:
            pc.note = body.note
    audit(
        db,
        action="inputs.product_cost_updated",
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        target=target_id,
        detail=body.model_dump(mode="json", exclude_none=True),
    )
    _changed(db, ctx, "product_costs")
    db.flush()
    return next(r for r in _with_valid_to(_active_costs(db, ctx.tenant_id, pc.seller_sku)) if r.id == target_id)


@router.delete("/product-costs/{cost_id}", status_code=204)
def delete_cost(cost_id: str, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> None:
    require(ctx, "inputs.write", resource="product_costs")
    pc = db.get(ProductCost, cost_id)
    if pc is None or pc.tenant_id != ctx.tenant_id or pc.deleted_at is not None:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy giá vốn")
    pc.deleted_at = now_utc()
    audit(db, action="inputs.product_cost_deleted", tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, target=cost_id)
    _changed(db, ctx, "product_costs")


def _selling_skus(ctx: AuthContext) -> list[tuple[str, str]]:
    """SKU đang bán của khách, đọc qua bộ máy chỉ số (spec 05 §6.4)."""
    from app.metrics.engine import selling_skus

    try:
        return selling_skus(ctx)
    except ApiError:
        return []


@router.get("/product-costs/template")
def cost_template(ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> Response:
    require(ctx, "inputs.read", resource="product_costs")
    content = build_template(_selling_skus(ctx))
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="mau_gia_von.xlsx"'},
    )


class UploadErrorOut(BaseModel):
    row: int
    column: str
    code: str
    message_vi: str
    warning: bool = False


class UploadOut(BaseModel):
    upload_id: str
    rows_total: int
    rows_ok: int
    rows_error: int
    errors: list[UploadErrorOut]


@router.post("/product-costs/upload", response_model=UploadOut)
async def upload_costs(
    file: UploadFile = File(...), ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)
) -> UploadOut:
    require(ctx, "inputs.write", resource="product_costs")
    content = await file.read()
    filename = file.filename or "upload"
    known = {s for s, _ in _selling_skus(ctx)} or None
    try:
        parsed = parse_costs_file(content, filename, known)
    except FileRejected as exc:
        raise ApiError(400, exc.code, exc.message_vi) from exc
    for r in parsed.rows:
        _upsert_cost(db, ctx, r.seller_sku, r.unit_cost_vnd, r.valid_from, r.note)
    rows_error = len(parsed.error_rows)
    job = UploadJob(
        tenant_id=ctx.tenant_id,
        kind="product_costs",
        filename=filename[:200],
        rows_total=parsed.total,
        rows_ok=len(parsed.rows),
        rows_error=rows_error,
        errors=[e.as_dict() for e in parsed.errors][:1000],
        created_by=ctx.user_id,
    )
    db.add(job)
    db.flush()
    audit(
        db,
        action="inputs.product_costs_uploaded",
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        target=job.id,
        detail={"rows_total": parsed.total, "rows_ok": len(parsed.rows), "rows_error": rows_error},
    )
    if parsed.rows:
        _changed(db, ctx, "product_costs")
    return UploadOut(
        upload_id=job.id,
        rows_total=parsed.total,
        rows_ok=len(parsed.rows),
        rows_error=rows_error,
        errors=[UploadErrorOut(**e.as_dict()) for e in parsed.errors],
    )


class MissingCostOut(BaseModel):
    seller_sku: str
    product_name: str | None
    net_revenue_30d: int


class MissingCostsOut(BaseModel):
    items: list[MissingCostOut]
    sku_count: int
    revenue_vnd: int
    data_as_of: str | None


@router.get("/product-costs/missing", response_model=MissingCostsOut)
def missing_costs(ctx: AuthContext = Depends(get_ctx)) -> MissingCostsOut:
    """SKU có doanh thu 30 ngày mà chưa có giá vốn (FR-INP-03), đọc qua bộ máy chỉ số."""
    require(ctx, "inputs.read", resource="product_costs")
    from app.metrics.engine import missing_cogs_skus

    items, as_of = missing_cogs_skus(ctx)
    return MissingCostsOut(
        items=[MissingCostOut(**i) for i in items],
        sku_count=len(items),
        revenue_vnd=sum(i["net_revenue_30d"] for i in items),
        data_as_of=as_of,
    )


# --------------------------------------------------------------------------- ngân sách quảng cáo


class BudgetOut(BaseModel):
    id: str
    platform: str
    month: str
    budget_vnd: int
    updated_at: datetime


class BudgetIn(BaseModel):
    platform: str
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    budget_vnd: Decimal = Field(ge=0, max_digits=18, decimal_places=2)


class BudgetUpdate(BaseModel):
    budget_vnd: Decimal = Field(ge=0, max_digits=18, decimal_places=2)


def _month(s: str) -> date:
    y, m = s.split("-")
    return date(int(y), int(m), 1)


def _budget_out(b: AdBudget) -> BudgetOut:
    return BudgetOut(
        id=b.id,
        platform=b.platform,
        month=b.month.strftime("%Y-%m"),
        budget_vnd=int(b.budget_vnd.quantize(Decimal("1"))),
        updated_at=b.updated_at,
    )


@router.get("/ad-budgets", response_model=list[BudgetOut])
def list_budgets(
    from_month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    to_month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    ctx: AuthContext = Depends(get_ctx),
    db: Session = Depends(get_db),
) -> list[BudgetOut]:
    require(ctx, "inputs.read", resource="ad_budgets")
    q = select(AdBudget).where(AdBudget.tenant_id == ctx.tenant_id, AdBudget.deleted_at.is_(None))
    if from_month:
        q = q.where(AdBudget.month >= _month(from_month))
    if to_month:
        q = q.where(AdBudget.month <= _month(to_month))
    return [_budget_out(b) for b in db.scalars(q.order_by(AdBudget.month, AdBudget.platform))]


@router.post("/ad-budgets", response_model=BudgetOut, status_code=201)
def create_budget(body: BudgetIn, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> BudgetOut:
    require(ctx, "inputs.write", resource="ad_budgets")
    platforms = ctx.tenant.ad_platforms()
    if body.platform not in platforms:
        # FR-INP-04: `platform` phải là nguồn quảng cáo khách có.
        raise ApiError(
            400,
            "PLATFORM_NOT_IN_TENANT",
            f"Nền tảng {body.platform} không phải nguồn quảng cáo của khách ({', '.join(platforms) or 'không có'})",
        )
    month = _month(body.month)
    stmt = insert(AdBudget).values(
        tenant_id=ctx.tenant_id,
        platform=body.platform,
        month=month,
        budget_vnd=body.budget_vnd,
        created_by=ctx.user_id,
        id=new_ulid(),
    )
    upsert = stmt.on_conflict_do_update(
        index_elements=["tenant_id", "platform", "month"],
        index_where=AdBudget.deleted_at.is_(None),
        set_={"budget_vnd": stmt.excluded.budget_vnd, "updated_at": now_utc()},
    ).returning(AdBudget.id)
    bid: str = db.execute(upsert).scalar_one()
    db.flush()
    audit(
        db,
        action="inputs.ad_budget_set",
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        target=bid,
        detail={"platform": body.platform, "month": body.month, "budget_vnd": str(body.budget_vnd)},
    )
    _changed(db, ctx, "ad_budgets")
    b = db.get(AdBudget, bid)
    assert b is not None
    db.refresh(b)
    return _budget_out(b)


@router.put("/ad-budgets/{budget_id}", response_model=BudgetOut)
def update_budget(
    budget_id: str, body: BudgetUpdate, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)
) -> BudgetOut:
    require(ctx, "inputs.write", resource="ad_budgets")
    b = db.get(AdBudget, budget_id)
    if b is None or b.tenant_id != ctx.tenant_id or b.deleted_at is not None:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy ngân sách")
    b.budget_vnd = body.budget_vnd
    audit(
        db,
        action="inputs.ad_budget_updated",
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        target=b.id,
        detail={"budget_vnd": str(body.budget_vnd)},
    )
    _changed(db, ctx, "ad_budgets")
    db.flush()
    db.refresh(b)
    return _budget_out(b)


@router.delete("/ad-budgets/{budget_id}", status_code=204)
def delete_budget(budget_id: str, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> None:
    require(ctx, "inputs.write", resource="ad_budgets")
    b = db.get(AdBudget, budget_id)
    if b is None or b.tenant_id != ctx.tenant_id or b.deleted_at is not None:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy ngân sách")
    b.deleted_at = now_utc()
    audit(db, action="inputs.ad_budget_deleted", tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, target=budget_id)
    _changed(db, ctx, "ad_budgets")
