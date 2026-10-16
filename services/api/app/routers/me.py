"""`GET /v1/me` (spec 05 §6.1): người dùng, danh sách khách và vai trò, `partner_id`, `staff_role`."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.context import CurrentUser, get_current_user, user_tenants
from app.auth.permissions import ACTIONS, allowed
from app.db import get_db
from app.db.models import PartnerUser, Tenant

router = APIRouter(prefix="/v1", tags=["me"])


class TenantRole(BaseModel):
    tenant_id: str
    name: str
    pack: str
    status: str
    role: str
    permissions: list[str]


class MeOut(BaseModel):
    user_id: str
    email: str | None
    display_name: str | None
    staff_role: str | None
    partner_id: str | None
    tenants: list[TenantRole]


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> MeOut:
    roles = dict(user_tenants(db, user))
    if user.staff_role:
        for t in db.scalars(select(Tenant).where(Tenant.status != "archived")):
            roles.setdefault(t.tenant_id, user.staff_role)
    tenants = {t.tenant_id: t for t in db.scalars(select(Tenant).where(Tenant.tenant_id.in_(list(roles))))}
    partner = db.scalar(select(PartnerUser.partner_id).where(PartnerUser.user_id == user.id))
    out = [
        TenantRole(
            tenant_id=tid,
            name=tenants[tid].name,
            pack=tenants[tid].pack,
            status=tenants[tid].status,
            role=role,
            permissions=[a for a in ACTIONS if allowed(role, a, resource="ad_budgets", pack=tenants[tid].pack)],
        )
        for tid, role in sorted(roles.items())
        if tid in tenants
    ]
    return MeOut(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        staff_role=user.staff_role,
        partner_id=partner,
        tenants=out,
    )
