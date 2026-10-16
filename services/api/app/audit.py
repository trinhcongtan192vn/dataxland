"""Nhật ký kiểm toán (NFR-10, NFR-11, spec 05 §7). Giữ tối thiểu 2 năm; không ghi giá trị bí mật hay PII người mua."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditLog


def audit(
    db: Session,
    *,
    action: str,
    tenant_id: str | None = None,
    actor_user_id: str | None = None,
    actor_service: str | None = None,
    target: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            action=action,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_service=actor_service,
            target=target,
            detail=detail or {},
        )
    )
