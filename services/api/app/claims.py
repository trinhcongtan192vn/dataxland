"""Đồng bộ Firebase custom claims `{role_hint, tenant_ids, partner_id}` khi quyền đổi (spec 05 §3.2).

Claims chỉ để giao diện hiện menu phù hợp; backend luôn đọc quyền từ Postgres.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.context import CurrentUser, user_tenants
from app.auth.firebase import set_custom_claims
from app.db.models import PartnerUser, User


def sync_claims(db: Session, user_id: str) -> None:
    u = db.get(User, user_id)
    if u is None:
        return
    cu = CurrentUser(u.id, u.firebase_uid, u.email, u.display_name, u.staff_role)
    roles = user_tenants(db, cu)
    partner = db.scalar(select(PartnerUser.partner_id).where(PartnerUser.user_id == u.id))
    set_custom_claims(
        u.firebase_uid,
        {
            "role_hint": u.staff_role or (roles[0][1] if roles else None),
            "tenant_ids": [t for t, _ in roles][:20],
            "partner_id": partner,
        },
    )
