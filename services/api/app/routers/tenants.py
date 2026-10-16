"""`GET /v1/tenants/{id}` (spec 05 §6.1, FR-OPS-01): cấu hình đã đồng bộ, bỏ `secret_ref`."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.context import CurrentUser, build_ctx, get_current_user, load_tenant
from app.db import get_db

router = APIRouter(prefix="/v1", tags=["tenants"])


class TenantOut(BaseModel):
    tenant_id: str
    name: str
    status: str
    pack: str
    config: dict[str, Any]
    config_hash: str
    synced_at: datetime


def public_config(config: dict[str, Any]) -> dict[str, Any]:
    clean = dict(config)
    clean["sources"] = [{k: v for k, v in s.items() if k != "secret_ref"} for s in config.get("sources", [])]
    return clean


@router.get("/tenants/{tenant_id}", response_model=TenantOut)
def get_tenant(
    tenant_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> TenantOut:
    build_ctx(db, user, tenant_id)  # người gọi phải có vai trò với khách đó
    t, _ = load_tenant(db, tenant_id)
    return TenantOut(
        tenant_id=t.tenant_id,
        name=t.name,
        status=t.status,
        pack=t.pack,
        config=public_config(t.config),
        config_hash=t.config_hash,
        synced_at=t.synced_at,
    )
