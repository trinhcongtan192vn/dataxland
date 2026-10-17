"""Hỏi đáp (spec 09 §3, §4, §6).

| Endpoint | Việc |
|---|---|
| `POST /v1/ask` | Câu hỏi từ cổng; 30 câu mỗi giờ mỗi người dùng |
| `POST /v1/ask/{id}/feedback` | Người hỏi chấm câu trả lời (`up`, `down`, null) |
| `GET /v1/ops/metric-requests` | Danh sách câu hỏi ngoài thư viện cho team |
| `PATCH /v1/ops/metric-requests/{id}` | Đổi trạng thái (`new`, `planned`, `done`, `declined`) |
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ask.engine import ask
from app.ask.render import to_markdown
from app.audit import audit
from app.auth.context import AuthContext, CurrentUser, get_ctx, get_current_user
from app.auth.permissions import require
from app.db import get_db
from app.db.models import AskLog, MetricRequest, Tenant
from app.errors import ApiError
from app.ratelimit import check_key_rate
from app.routers.ops import require_staff

router = APIRouter(tags=["ask"])

PORTAL_LIMIT = (30, 3600)


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    conversation_id: str | None = Field(default=None, max_length=64)


class AskOut(BaseModel):
    ask_id: str
    conversation_id: str
    answer_vi: str
    answer_md: str
    citations: list[dict[str, Any]]
    missing_metric: dict[str, str] | None
    refused_reason: str | None
    cached: bool


@router.post("/v1/ask", response_model=AskOut)
def post_ask(body: AskIn, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, Any]:
    require(ctx, "metrics.read")
    check_key_rate(db, f"ask:{ctx.user_id}", *PORTAL_LIMIT)
    res = ask(db, ctx, body.question, "portal", body.conversation_id)
    return {**res.as_dict(), "answer_md": to_markdown(res.answer_vi, res.citations)}


class FeedbackIn(BaseModel):
    feedback: Literal["up", "down"] | None


@router.post("/v1/ask/{ask_id}/feedback", status_code=204)
def post_feedback(
    ask_id: str, body: FeedbackIn, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)
) -> None:
    row = db.get(AskLog, ask_id)
    if row is None or row.tenant_id != ctx.tenant_id or row.user_id != ctx.user_id:
        raise ApiError(404, "ASK_NOT_FOUND", "Không tìm thấy câu hỏi")
    row.feedback = body.feedback


class MetricRequestOut(BaseModel):
    id: str
    tenant_id: str
    tenant_name: str
    question: str
    description_vi: str
    count: int
    status: str
    created_at: datetime
    updated_at: datetime


@router.get("/v1/ops/metric-requests", response_model=list[MetricRequestOut])
def list_metric_requests(
    status: Literal["new", "planned", "done", "declined"] | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    require_staff(user, "ops.read")
    q = select(MetricRequest)
    if status:
        q = q.where(MetricRequest.status == status)
    rows = list(db.scalars(q.order_by(MetricRequest.count.desc(), MetricRequest.updated_at.desc()).limit(500)))
    names = {t.tenant_id: t.name for t in db.scalars(select(Tenant))}
    return [
        {
            "id": r.id,
            "tenant_id": r.tenant_id,
            "tenant_name": names.get(r.tenant_id, r.tenant_id),
            "question": r.question,
            "description_vi": r.description_vi,
            "count": r.count,
            "status": r.status,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


class MetricRequestPatch(BaseModel):
    status: Literal["new", "planned", "done", "declined"]


@router.patch("/v1/ops/metric-requests/{request_id}", status_code=204)
def patch_metric_request(
    request_id: str,
    body: MetricRequestPatch,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    require_staff(user, "ops.write")
    row = db.get(MetricRequest, request_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy yêu cầu chỉ số")
    old = row.status
    row.status = body.status
    audit(
        db,
        action="metric_request.status",
        tenant_id=row.tenant_id,
        actor_user_id=user.id,
        target=row.id,
        detail={"from": old, "to": body.status},
    )
