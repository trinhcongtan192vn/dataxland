"""Hàng chờ ghép định danh (spec 10 §5) và endpoint nội bộ cho `identity_worker`.

Data lead (`ops.read`/`ops.write`, theo `X-Tenant-Id`): xem cặp, duyệt, từ chối, duyệt hàng loạt, gỡ cặp đã duyệt.
Mọi quyết định ghi `audit_log` và phát `identity.changed` để pipeline ghi lại `identity_map` và chạy lại dbt.
Gợi ý không bao giờ tự duyệt; chỉ cặp theo quy tắc có `approved_by = 'system'`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.context import AuthContext, get_ctx
from app.auth.internal import ServiceCaller, require_service
from app.auth.permissions import require
from app.db import get_db
from app.db.models import AuditLog, IdentityMatch
from app.errors import ApiError
from dx_common.events import publish
from dx_common.timeutil import now_utc

router = APIRouter(tags=["identity"])


class MatchOut(BaseModel):
    id: str
    entity: str
    left: dict[str, Any]
    right: dict[str, Any]
    method: str
    score: float | None
    reason_vi: str | None
    status: str
    decided_by: str | None
    decided_at: datetime | None
    created_at: datetime


def _out(m: IdentityMatch) -> MatchOut:
    return MatchOut(
        id=m.id,
        entity=m.entity,
        left=m.left,
        right=m.right,
        method=m.method,
        score=float(m.score) if m.score is not None else None,
        reason_vi=m.reason_vi,
        status=m.status,
        decided_by=m.decided_by,
        decided_at=m.decided_at,
        created_at=m.created_at,
    )


@router.get("/v1/identity/matches", response_model=list[MatchOut])
def list_matches(
    status: str = Query(default="proposed"), ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)
) -> list[MatchOut]:
    require(ctx, "ops.read")
    q = select(IdentityMatch).where(IdentityMatch.tenant_id == ctx.tenant_id)
    if status != "all":
        q = q.where(IdentityMatch.status == status)
    return [_out(m) for m in db.scalars(q.order_by(IdentityMatch.score.desc().nulls_last()).limit(500))]


def _decide(db: Session, ctx: AuthContext, ids: list[str], action: str) -> list[IdentityMatch]:
    allowed = {"approve": ("proposed",), "reject": ("proposed",), "undo": ("approved",)}[action]
    new = {"approve": "approved", "reject": "rejected", "undo": "undone"}[action]
    rows = list(
        db.scalars(select(IdentityMatch).where(IdentityMatch.id.in_(ids), IdentityMatch.tenant_id == ctx.tenant_id))
    )
    if len(rows) != len(set(ids)):
        raise ApiError(404, "MATCH_NOT_FOUND", "Không tìm thấy cặp ghép")
    bad = [m.id for m in rows if m.status not in allowed]
    if bad:
        raise ApiError(409, "MATCH_STATE", f"Cặp {', '.join(bad[:5])} không ở trạng thái cho phép {action}")
    now = now_utc()
    for m in rows:
        m.status, m.decided_by, m.decided_at = new, ctx.user_id, now
        audit(
            db,
            action=f"identity.{action}",
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            target=m.id,
            detail={"entity": m.entity, "method": m.method, "score": float(m.score) if m.score is not None else None},
        )
    db.flush()
    publish("identity.changed", ctx.tenant_id, {"entity": "product"}, "s3-identity", bind=db)
    return rows


@router.post("/v1/identity/matches/{match_id}/approve", response_model=MatchOut)
def approve(match_id: str, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> MatchOut:
    require(ctx, "ops.write")
    return _out(_decide(db, ctx, [match_id], "approve")[0])


@router.post("/v1/identity/matches/{match_id}/reject", response_model=MatchOut)
def reject(match_id: str, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> MatchOut:
    require(ctx, "ops.write")
    return _out(_decide(db, ctx, [match_id], "reject")[0])


@router.post("/v1/identity/matches/{match_id}/undo", response_model=MatchOut)
def undo(match_id: str, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> MatchOut:
    require(ctx, "ops.write")
    return _out(_decide(db, ctx, [match_id], "undo")[0])


class BulkIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=500)
    action: Literal["approve", "reject"]


@router.post("/v1/identity/matches/bulk", response_model=list[MatchOut])
def bulk(body: BulkIn, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> list[MatchOut]:
    require(ctx, "ops.write")
    return [_out(m) for m in _decide(db, ctx, body.ids, body.action)]


# --------------------------------------------------------------------------- nội bộ (identity_worker)


class TenantIn(BaseModel):
    tenant_id: str


@router.post("/v1/internal/identity/matches/keys")
def internal_keys(
    body: TenantIn, _: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Cặp đã có (mọi trạng thái) để worker không gợi ý lại; thời điểm lần gợi ý gần nhất (tối đa một lần/ngày)."""
    keys = db.scalars(select(IdentityMatch.pair_key).where(IdentityMatch.tenant_id == body.tenant_id))
    last = db.scalar(
        select(func.max(AuditLog.created_at)).where(
            AuditLog.tenant_id == body.tenant_id, AuditLog.action == "identity.suggest_run"
        )
    )
    return {"pair_keys": list(keys), "last_suggest_at": last.isoformat() if last else None}


class MatchIn(BaseModel):
    entity: Literal["product"]
    left: dict[str, Any]
    right: dict[str, Any]
    pair_key: str
    method: str
    score: float | None = None
    reason_vi: str | None = None
    status: Literal["proposed", "approved"]


class MatchesIn(BaseModel):
    tenant_id: str
    run_id: str | None = None
    suggest_run: bool = False
    matches: list[MatchIn] = Field(default_factory=list)


@router.post("/v1/internal/identity/matches")
def internal_upsert(
    body: MatchesIn, _: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)
) -> dict[str, int]:
    """Ghi cặp theo quy tắc (`approved`, `system`) và gợi ý (`proposed`); cặp đã có thì giữ quyết định của người."""
    created = proposed = 0
    for m in body.matches:
        stmt = (
            insert(IdentityMatch)
            .values(
                tenant_id=body.tenant_id,
                entity=m.entity,
                left=m.left,
                right=m.right,
                pair_key=m.pair_key,
                method=m.method,
                score=m.score,
                reason_vi=m.reason_vi,
                status=m.status,
                decided_by="system" if m.status == "approved" else None,
                decided_at=now_utc() if m.status == "approved" else None,
                run_id=body.run_id,
            )
            .on_conflict_do_nothing(constraint="uq_identity_matches_pair")
            .returning(IdentityMatch.id)
        )
        mid = db.execute(stmt).scalar()
        if mid is None:
            continue
        created += 1
        if m.status == "proposed":
            proposed += 1
            publish(
                "match.proposed",
                body.tenant_id,
                {"match_id": mid, "entity": m.entity, "score": m.score or 0},
                "s3-identity",
                bind=db,
            )
    if body.suggest_run:
        audit(
            db,
            action="identity.suggest_run",
            tenant_id=body.tenant_id,
            actor_service="dagster",
            detail={"run_id": body.run_id, "created": created, "proposed": proposed},
        )
    return {"created": created, "proposed": proposed}


@router.post("/v1/internal/identity/approved")
def internal_approved(
    body: TenantIn, _: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)
) -> dict[str, Any]:
    rows = db.scalars(
        select(IdentityMatch).where(IdentityMatch.tenant_id == body.tenant_id, IdentityMatch.status == "approved")
    )
    return {
        "pairs": [
            {
                "left": f"{m.left['source']}:{m.left['source_id']}",
                "right": f"{m.right['source']}:{m.right['source_id']}",
                "method": m.method,
            }
            for m in rows
        ]
    }
