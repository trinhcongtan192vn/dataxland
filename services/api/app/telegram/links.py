"""Gỡ liên kết Telegram (spec 08 §3.5): phát `telegram.unlinked`, ghi `audit_log`."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.db.models import TelegramLink
from dx_common.events import publish
from dx_common.timeutil import now_utc

REASONS = ("user_unlink", "owner_removed", "access_lost", "bot_removed", "bot_blocked")


def revoke_link(db: Session, link: TelegramLink, reason: str, actor_user_id: str | None = None) -> None:
    if link.status != "active":
        return
    if reason not in REASONS:
        raise ValueError(reason)
    link.status = "revoked"
    link.revoked_at = now_utc()
    link.revoked_reason = reason
    db.flush()
    publish("telegram.unlinked", link.tenant_id, {"link_id": link.id, "chat_type": link.chat_type}, "s6b-bot", bind=db)
    audit(
        db,
        action="telegram.unlinked",
        tenant_id=link.tenant_id,
        actor_user_id=actor_user_id,
        actor_service=None if actor_user_id else "api",
        target=link.id,
        detail={"reason": reason},
    )


def revoke_user_links(
    db: Session, tenant_id: str, user_ids: Iterable[str], reason: str, actor_user_id: str | None = None
) -> int:
    ids = list(user_ids)
    if not ids:
        return 0
    links = db.scalars(
        select(TelegramLink).where(
            TelegramLink.tenant_id == tenant_id, TelegramLink.user_id.in_(ids), TelegramLink.status == "active"
        )
    ).all()
    for link in links:
        revoke_link(db, link, reason, actor_user_id)
    return len(links)
