"""`AuthContext` và dependency `get_ctx()` (spec 05 §3.2, §3.4).

Vai trò hiệu lực đọc từ Postgres ở mỗi request, không cache, nên thu quyền có hiệu lực ngay ở lần gọi kế tiếp
(FR-AUTH-04). Không đoạn code nào lấy `tenant_id` từ tham số mà không đối chiếu quyền (spec 00 §3.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.firebase import InvalidToken, get_token_verifier
from app.auth.internal import bearer, is_internal_token
from app.db import get_db
from app.db.models import Invitation, Membership, PartnerGrant, PartnerUser, TelegramLink, Tenant, User
from app.errors import ApiError
from app.ratelimit import check_user_rate
from dx_common.logging import tenant_id_var
from dx_common.tenants import TenantConfig
from dx_common.timeutil import now_utc

Caller = Literal["user", "bot", "internal"]


@dataclass
class CurrentUser:
    id: str
    firebase_uid: str
    email: str | None
    display_name: str | None
    staff_role: str | None


@dataclass
class AuthContext:
    tenant_id: str
    role: str
    pack: str
    dataset_prefix: str
    tenant: TenantConfig
    caller: Caller = "user"
    user_id: str | None = None
    metric_scope: Literal["all"] | list[str] = "all"
    partner_id: str | None = None
    staff_role: str | None = None
    telegram_link_id: str | None = None
    chat_id: int | None = None
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def is_staff(self) -> bool:
        return self.role in ("data_lead", "engineer")


# --------------------------------------------------------------------------- người dùng


def _accept_pending_invitations(db: Session, user: User) -> None:
    if not user.email:
        return
    now = now_utc()
    invs = db.scalars(
        select(Invitation).where(
            Invitation.email == user.email.lower(),
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > now,
        )
    ).all()
    for inv in invs:
        exists = db.scalar(
            select(Membership).where(Membership.user_id == user.id, Membership.tenant_id == inv.tenant_id)
        )
        if exists is None:
            db.add(
                Membership(
                    user_id=user.id,
                    tenant_id=inv.tenant_id,
                    role=inv.role,
                    metric_allowlist=inv.metric_allowlist if inv.role == "member" else None,
                    invited_by=inv.invited_by,
                )
            )
        inv.accepted_at = now
        audit(db, action="invitation.accepted", tenant_id=inv.tenant_id, actor_user_id=user.id, target=inv.id)


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> CurrentUser:
    token = bearer(authorization)
    if not token:
        raise ApiError(401, "UNAUTHENTICATED", "Cần đăng nhập")
    if is_internal_token(token):
        raise ApiError(403, "USER_REQUIRED", "Endpoint này cần token người dùng")
    try:
        vt = get_token_verifier().verify(token)
    except InvalidToken as exc:
        raise ApiError(401, "INVALID_TOKEN", "Token không hợp lệ, hết hạn hoặc đã bị thu hồi") from exc
    user = db.scalar(select(User).where(User.firebase_uid == vt.uid))
    if user is None:
        user = User(
            firebase_uid=vt.uid,
            email=(vt.email or "").lower() or None,
            display_name=vt.name,
        )
        db.add(user)
        db.flush()
        audit(
            db,
            action="user.first_login",
            actor_user_id=user.id,
            target=user.id,
            detail={"provider": vt.sign_in_provider},
        )
        _accept_pending_invitations(db, user)
        db.flush()
    elif vt.email and user.email != vt.email.lower():
        user.email = vt.email.lower()
    if user.disabled:
        raise ApiError(403, "USER_DISABLED", "Tài khoản đã bị khóa")
    check_user_rate(db, user.id, request.url.path, request.method)
    request.state.user_id = user.id
    return CurrentUser(user.id, user.firebase_uid, user.email, user.display_name, user.staff_role)


# --------------------------------------------------------------------------- khách và vai trò


def load_tenant(db: Session, tenant_id: str) -> tuple[Tenant, TenantConfig]:
    t = db.get(Tenant, tenant_id)
    if t is None or t.status == "archived":
        raise ApiError(404, "TENANT_NOT_FOUND", "Không tìm thấy khách")
    return t, TenantConfig.model_validate(t.config)


def user_tenants(db: Session, user: CurrentUser) -> list[tuple[str, str]]:
    """Các khách người dùng có vai trò (qua membership hoặc partner_grants đang hiệu lực), không gồm quyền nhân viên."""
    out: dict[str, str] = {}
    for m in db.scalars(select(Membership).where(Membership.user_id == user.id)):
        out[m.tenant_id] = m.role
    partner_ids = [p.partner_id for p in db.scalars(select(PartnerUser).where(PartnerUser.user_id == user.id))]
    if partner_ids:
        for g in db.scalars(
            select(PartnerGrant).where(PartnerGrant.partner_id.in_(partner_ids), PartnerGrant.revoked_at.is_(None))
        ):
            out.setdefault(g.tenant_id, "partner")
    active = {
        t.tenant_id
        for t in db.scalars(select(Tenant).where(Tenant.tenant_id.in_(list(out)), Tenant.status != "archived"))
    }
    return sorted((tid, role) for tid, role in out.items() if tid in active)


def resolve_role(
    db: Session, user_id: str, staff_role: str | None, tenant_id: str
) -> tuple[str, list[str] | None, str | None]:
    """Trả (vai trò, metric_allowlist, partner_id). Không có vai trò → 403 TENANT_FORBIDDEN."""
    m = db.scalar(select(Membership).where(Membership.user_id == user_id, Membership.tenant_id == tenant_id))
    if m is not None:
        return m.role, (m.metric_allowlist if m.role == "member" else None), None
    g = db.execute(
        select(PartnerGrant.partner_id)
        .join(PartnerUser, PartnerUser.partner_id == PartnerGrant.partner_id)
        .where(PartnerUser.user_id == user_id, PartnerGrant.tenant_id == tenant_id, PartnerGrant.revoked_at.is_(None))
    ).first()
    if g is not None:
        return "partner", None, g[0]
    if staff_role in ("data_lead", "engineer"):
        return staff_role, None, None
    raise ApiError(403, "TENANT_FORBIDDEN", "Bạn không có quyền với khách này")


def build_ctx(db: Session, user: CurrentUser, tenant_id: str, caller: Caller = "user") -> AuthContext:
    role, allowlist, partner_id = resolve_role(db, user.id, user.staff_role, tenant_id)
    _, cfg = load_tenant(db, tenant_id)
    scope: Literal["all"] | list[str] = allowlist if (role == "member" and allowlist is not None) else "all"
    tenant_id_var.set(tenant_id)
    return AuthContext(
        tenant_id=tenant_id,
        role=role,
        pack=cfg.pack,
        dataset_prefix=cfg.dataset_prefix,
        tenant=cfg,
        caller=caller,
        user_id=user.id,
        metric_scope=scope,
        partner_id=partner_id,
        staff_role=user.staff_role,
    )


def get_ctx(
    x_tenant_id: str | None = Header(default=None),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuthContext:
    tenant_id = x_tenant_id
    if not tenant_id:
        mine = user_tenants(db, user)
        if len(mine) == 1:
            tenant_id = mine[0][0]
        else:
            raise ApiError(400, "TENANT_REQUIRED", "Cần chọn khách (header X-Tenant-Id)")
    return build_ctx(db, user, tenant_id)


def internal_ctx(db: Session, tenant_id: str, dataset_prefix: str | None = None) -> AuthContext:
    """Ngữ cảnh nội bộ của một khách cho job nền (dựng báo cáo, bất thường, kiểm tra sức khỏe)."""
    if tenant_id.startswith("hc_"):
        from app.healthchecks.tenant import healthcheck_tenant_config

        cfg = healthcheck_tenant_config(db, tenant_id)
    else:
        _, cfg = load_tenant(db, tenant_id)
    tenant_id_var.set(tenant_id)
    return AuthContext(
        tenant_id=tenant_id,
        role="internal",
        pack=cfg.pack,
        dataset_prefix=dataset_prefix or cfg.dataset_prefix,
        tenant=cfg,
        caller="internal",
    )


# --------------------------------------------------------------------------- bot gọi thay người dùng


def bot_ctx_for_link(db: Session, link: TelegramLink) -> AuthContext:
    """Spec 05 §3.4: dựng ngữ cảnh cho liên kết; mất quyền thì gỡ liên kết và trả 403 TELEGRAM_NOT_LINKED."""
    from app.telegram.links import revoke_link

    user = db.get(User, link.user_id)
    if user is None or user.disabled:
        revoke_link(db, link, "access_lost")
        raise ApiError(403, "TELEGRAM_NOT_LINKED", "Chat chưa liên kết")
    cu = CurrentUser(user.id, user.firebase_uid, user.email, user.display_name, user.staff_role)
    if link.chat_type == "private":
        try:
            ctx = build_ctx(db, cu, link.tenant_id, caller="bot")
        except ApiError as exc:
            if exc.code in ("TENANT_FORBIDDEN", "TENANT_NOT_FOUND"):
                revoke_link(db, link, "access_lost")
                raise ApiError(403, "TELEGRAM_NOT_LINKED", "Chat chưa liên kết") from exc
            raise
    else:
        m = db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.tenant_id == link.tenant_id))
        if m is None or m.role != "owner":
            revoke_link(db, link, "owner_removed")
            raise ApiError(403, "TELEGRAM_NOT_LINKED", "Nhóm chưa liên kết")
        _, cfg = load_tenant(db, link.tenant_id)
        ctx = AuthContext(
            tenant_id=link.tenant_id,
            role="group",
            pack=cfg.pack,
            dataset_prefix=cfg.dataset_prefix,
            tenant=cfg,
            caller="bot",
            user_id=user.id,
            metric_scope=list(link.metric_scope or []),
        )
    ctx.telegram_link_id = link.id
    ctx.chat_id = link.chat_id
    tenant_id_var.set(link.tenant_id)
    return ctx
