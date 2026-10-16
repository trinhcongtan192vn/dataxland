"""Mời và gỡ member, giới hạn chỉ số member được xem (FR-AUTH-03, spec 05 §5.1)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.context import AuthContext, CurrentUser, get_ctx, get_current_user, load_tenant
from app.auth.permissions import require
from app.claims import sync_claims
from app.db import get_db
from app.db.models import Invitation, Membership, User
from app.errors import ApiError
from app.metrics.registry import get_registry
from app.notify.direct import send_email_now
from app.notify.types import Button
from app.telegram.links import revoke_user_links
from dx_common.config import get_settings
from dx_common.ids import random_token
from dx_common.timeutil import now_utc, to_vn

router = APIRouter(prefix="/v1", tags=["members"])

INVITE_TTL = timedelta(days=7)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class MemberOut(BaseModel):
    user_id: str
    email: str | None
    display_name: str | None
    role: str
    metric_allowlist: list[str] | None


class InvitationOut(BaseModel):
    id: str
    email: str
    role: str
    metric_allowlist: list[str] | None
    expires_at: datetime
    invite_url: str | None = None
    email_sent: bool | None = None


class MembersOut(BaseModel):
    members: list[MemberOut]
    invitations: list[InvitationOut]


class InviteIn(BaseModel):
    email: EmailStr
    role: str = Field(default="member", pattern="^(member|owner)$")
    metric_allowlist: list[str] | None = None


class AllowlistIn(BaseModel):
    metric_allowlist: list[str]


class AcceptIn(BaseModel):
    token: str


def _check_allowlist(ctx: AuthContext, metrics: list[str]) -> list[str]:
    """`metric_allowlist` chỉ nhận chỉ số không ẩn của gói khách (spec 05 §5.1)."""
    reg = get_registry()
    allowed = {m.metric for m in reg.visible_for_tenant(ctx.tenant)}
    bad = [m for m in metrics if m not in allowed]
    if bad:
        raise ApiError(400, "METRIC_NOT_ALLOWED", f"Chỉ số không thuộc gói của khách: {', '.join(bad)}")
    return sorted(set(metrics))


@router.get("/members", response_model=MembersOut)
def list_members(ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> MembersOut:
    require(ctx, "users.manage")
    rows = db.execute(
        select(Membership, User).join(User, User.id == Membership.user_id).where(Membership.tenant_id == ctx.tenant_id)
    ).all()
    invs = db.scalars(
        select(Invitation).where(
            Invitation.tenant_id == ctx.tenant_id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > now_utc(),
        )
    ).all()
    return MembersOut(
        members=[
            MemberOut(
                user_id=u.id,
                email=u.email,
                display_name=u.display_name,
                role=m.role,
                metric_allowlist=m.metric_allowlist,
            )
            for m, u in sorted(rows, key=lambda r: (r[0].role != "owner", r[1].email or ""))
        ],
        invitations=[
            InvitationOut(
                id=i.id, email=i.email, role=i.role, metric_allowlist=i.metric_allowlist, expires_at=i.expires_at
            )
            for i in invs
        ],
    )


@router.post("/members/invitations", response_model=InvitationOut, status_code=201)
def invite(
    body: InviteIn,
    ctx: AuthContext = Depends(get_ctx),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> InvitationOut:
    require(ctx, "users.manage")
    if body.role == "owner" and ctx.role != "data_lead":
        raise ApiError(403, "PERMISSION_DENIED", "Chỉ trưởng nhóm data mời được owner")
    allowlist = _check_allowlist(ctx, body.metric_allowlist or []) if body.role == "member" else None
    if body.role == "member" and not allowlist:
        raise ApiError(400, "ALLOWLIST_REQUIRED", "Cần chọn ít nhất một chỉ số member được xem")
    email = body.email.lower()
    already = db.scalar(
        select(Membership)
        .join(User, User.id == Membership.user_id)
        .where(Membership.tenant_id == ctx.tenant_id, func.lower(User.email) == email)
    )
    if already is not None:
        raise ApiError(409, "ALREADY_MEMBER", "Người này đã là thành viên")
    token = random_token(32)
    inv = Invitation(
        tenant_id=ctx.tenant_id,
        email=email,
        role=body.role,
        metric_allowlist=allowlist,
        token_hash=_hash(token),
        invited_by=ctx.user_id,
        expires_at=now_utc() + INVITE_TTL,
    )
    db.add(inv)
    db.flush()
    audit(
        db,
        action="member.invited",
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        target=inv.id,
        detail={"role": body.role, "metric_allowlist": allowlist},
    )
    url = f"{get_settings().dx_public_base_url.rstrip('/')}/invite/{token}"
    t, _ = load_tenant(db, ctx.tenant_id)
    result = send_email_now(
        email,
        "invitation",
        {
            "tenant_name": t.name,
            "role_vi": "chủ shop" if body.role == "owner" else "thành viên",
            "invite_url": url,
            "inviter_name": user.display_name or user.email,
            "expires_on": to_vn(inv.expires_at).date(),
        },
        [Button("Nhận lời mời", url)],
    )
    return InvitationOut(
        id=inv.id,
        email=email,
        role=inv.role,
        metric_allowlist=allowlist,
        expires_at=inv.expires_at,
        invite_url=url,
        email_sent=result.ok,
    )


@router.delete("/members/invitations/{invitation_id}", status_code=204)
def revoke_invitation(invitation_id: str, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> None:
    require(ctx, "users.manage")
    inv = db.get(Invitation, invitation_id)
    if inv is None or inv.tenant_id != ctx.tenant_id:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy lời mời")
    inv.revoked_at = now_utc()
    audit(db, action="member.invitation_revoked", tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, target=inv.id)


@router.put("/members/{user_id}", response_model=MemberOut)
def update_member(
    user_id: str, body: AllowlistIn, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)
) -> MemberOut:
    require(ctx, "users.manage")
    m = db.scalar(select(Membership).where(Membership.tenant_id == ctx.tenant_id, Membership.user_id == user_id))
    if m is None:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy thành viên")
    if m.role != "member":
        raise ApiError(400, "NOT_A_MEMBER", "Chỉ giới hạn chỉ số cho member")
    allowlist = _check_allowlist(ctx, body.metric_allowlist)
    if not allowlist:
        raise ApiError(400, "ALLOWLIST_REQUIRED", "Cần chọn ít nhất một chỉ số")
    m.metric_allowlist = allowlist
    audit(
        db,
        action="member.allowlist_changed",
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        target=user_id,
        detail={"metric_allowlist": allowlist},
    )
    u = db.get(User, user_id)
    return MemberOut(
        user_id=user_id,
        email=u.email if u else None,
        display_name=u.display_name if u else None,
        role=m.role,
        metric_allowlist=allowlist,
    )


@router.delete("/members/{user_id}", status_code=204)
def remove_member(user_id: str, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> None:
    require(ctx, "users.manage")
    m = db.scalar(select(Membership).where(Membership.tenant_id == ctx.tenant_id, Membership.user_id == user_id))
    if m is None:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy thành viên")
    if m.role == "owner":
        owners = db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.tenant_id == ctx.tenant_id, Membership.role == "owner")
        )
        if (owners or 0) <= 1:
            raise ApiError(409, "LAST_OWNER", "Không gỡ được owner duy nhất của khách")
    db.delete(m)
    db.flush()
    # Gỡ luôn liên kết Telegram của người đó với khách này (spec 05 §5.1). Liên kết nhóm do owner bị gỡ cũng mất.
    reason = "owner_removed" if m.role == "owner" else "access_lost"
    revoke_user_links(db, ctx.tenant_id, [user_id], reason, ctx.user_id)
    audit(
        db,
        action="member.removed",
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        target=user_id,
        detail={"role": m.role},
    )
    sync_claims(db, user_id)


@router.post("/invitations/accept", response_model=MemberOut)
def accept_invitation(
    body: AcceptIn, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> MemberOut:
    inv = db.scalar(select(Invitation).where(Invitation.token_hash == _hash(body.token)))
    now = now_utc()
    if inv is None or inv.revoked_at is not None:
        raise ApiError(404, "INVITATION_INVALID", "Lời mời không hợp lệ")
    if inv.accepted_at is not None or inv.expires_at <= now:
        raise ApiError(410, "INVITATION_EXPIRED", "Lời mời đã dùng hoặc hết hạn")
    if (user.email or "").lower() != inv.email:
        raise ApiError(
            403, "INVITATION_EMAIL_MISMATCH", "Lời mời dành cho email khác. Hãy đăng nhập đúng email được mời."
        )
    m = db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.tenant_id == inv.tenant_id))
    if m is None:
        m = Membership(
            user_id=user.id,
            tenant_id=inv.tenant_id,
            role=inv.role,
            metric_allowlist=inv.metric_allowlist if inv.role == "member" else None,
            invited_by=inv.invited_by,
        )
        db.add(m)
    inv.accepted_at = now
    db.flush()
    audit(db, action="invitation.accepted", tenant_id=inv.tenant_id, actor_user_id=user.id, target=inv.id)
    sync_claims(db, user.id)
    return MemberOut(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=m.role,
        metric_allowlist=m.metric_allowlist,
    )
