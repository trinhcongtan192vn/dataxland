"""Owner cấp và thu quyền cho agency (FR-AUTH-04, spec 05 §5.3). Thu quyền có hiệu lực ở lần gọi API kế tiếp."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.context import AuthContext, get_ctx
from app.auth.permissions import require
from app.claims import sync_claims
from app.db import get_db
from app.db.models import Partner, PartnerGrant, PartnerUser
from app.errors import ApiError
from app.telegram.links import revoke_user_links
from dx_common.timeutil import now_utc

router = APIRouter(prefix="/v1/partners", tags=["partners"])


class PartnerOut(BaseModel):
    partner_id: str
    name: str


class GrantOut(BaseModel):
    id: str
    partner_id: str
    partner_name: str
    granted_by: str | None
    granted_at: datetime


class GrantIn(BaseModel):
    partner_id: str


@router.get("", response_model=list[PartnerOut])
def list_partners(ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> list[PartnerOut]:
    require(ctx, "partners.manage")
    return [
        PartnerOut(partner_id=p.partner_id, name=p.name) for p in db.scalars(select(Partner).order_by(Partner.name))
    ]


@router.get("/grants", response_model=list[GrantOut])
def list_grants(ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> list[GrantOut]:
    require(ctx, "partners.manage")
    rows = db.execute(
        select(PartnerGrant, Partner)
        .join(Partner, Partner.partner_id == PartnerGrant.partner_id)
        .where(PartnerGrant.tenant_id == ctx.tenant_id, PartnerGrant.revoked_at.is_(None))
    ).all()
    return [
        GrantOut(
            id=g.id, partner_id=g.partner_id, partner_name=p.name, granted_by=g.granted_by, granted_at=g.granted_at
        )
        for g, p in rows
    ]


@router.post("/grants", response_model=GrantOut, status_code=201)
def grant(body: GrantIn, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> GrantOut:
    require(ctx, "partners.manage")
    p = db.get(Partner, body.partner_id)
    if p is None:
        raise ApiError(404, "PARTNER_NOT_FOUND", "Không tìm thấy agency")
    existing = db.scalar(
        select(PartnerGrant).where(
            PartnerGrant.tenant_id == ctx.tenant_id,
            PartnerGrant.partner_id == p.partner_id,
            PartnerGrant.revoked_at.is_(None),
        )
    )
    if existing is not None:
        raise ApiError(409, "ALREADY_GRANTED", "Agency đã có quyền với khách này")
    g = PartnerGrant(tenant_id=ctx.tenant_id, partner_id=p.partner_id, granted_by=ctx.user_id, granted_at=now_utc())
    db.add(g)
    db.flush()
    audit(db, action="partner.granted", tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, target=p.partner_id)
    for uid in db.scalars(select(PartnerUser.user_id).where(PartnerUser.partner_id == p.partner_id)):
        sync_claims(db, uid)
    return GrantOut(
        id=g.id, partner_id=p.partner_id, partner_name=p.name, granted_by=g.granted_by, granted_at=g.granted_at
    )


@router.delete("/grants/{grant_id}", status_code=204)
def revoke(grant_id: str, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> None:
    require(ctx, "partners.manage")
    g = db.get(PartnerGrant, grant_id)
    if g is None or g.tenant_id != ctx.tenant_id or g.revoked_at is not None:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy quyền đang hiệu lực")
    g.revoked_at = now_utc()
    g.revoked_by = ctx.user_id
    db.flush()
    # Gỡ liên kết Telegram của người dùng agency với khách (spec 05 §5.3).
    users = list(db.scalars(select(PartnerUser.user_id).where(PartnerUser.partner_id == g.partner_id)))
    revoke_user_links(db, ctx.tenant_id, users, "access_lost", ctx.user_id)
    audit(db, action="partner.revoked", tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, target=g.partner_id)
    for uid in users:
        sync_claims(db, uid)
