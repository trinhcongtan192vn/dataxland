"""Trang agency (spec 06 §8, FR-AGY-01, FR-AGY-02).

`GET /v1/partner/tenants`: với mỗi khách có `partner_grants` đang hiệu lực cho agency của người gọi, gọi bộ máy chỉ số
**riêng cho từng khách** (mỗi lần một `AuthContext`), trả chi tiêu tháng, tiến độ ngân sách, ROAS thật và cờ cần chú ý.
Không truy vấn nào đọc hai khách cùng lúc. Khách thu quyền thì biến mất ở lần gọi kế tiếp.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.context import CurrentUser, build_ctx, get_current_user
from app.db import get_db
from app.db.models import PartnerGrant, PartnerUser, Tenant
from app.errors import ApiError
from app.metrics.engine import QueryIn, query
from app.metrics.flags import compute_flags
from dx_common.logging import get_logger

router = APIRouter(prefix="/v1/partner", tags=["partner"])
log = get_logger(__name__)


class PartnerTenant(BaseModel):
    tenant_id: str
    name: str
    pack: str
    ad_spend_mtd: float | None
    budget_pacing: float | None
    roas_blended: float | None
    flags: list[dict[str, Any]]
    data_as_of: str | None
    error: str | None = None


@router.get("/tenants", response_model=list[PartnerTenant])
def partner_tenants(
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[PartnerTenant]:
    partner_id = db.scalar(select(PartnerUser.partner_id).where(PartnerUser.user_id == user.id))
    if partner_id is None:
        raise ApiError(403, "PERMISSION_DENIED", "Tài khoản không thuộc agency nào")
    grants = db.scalars(
        select(PartnerGrant.tenant_id).where(PartnerGrant.partner_id == partner_id, PartnerGrant.revoked_at.is_(None))
    )
    out: list[PartnerTenant] = []
    for tid in sorted(set(grants)):
        t = db.get(Tenant, tid)
        if t is None or t.status == "archived":
            continue
        ctx = build_ctx(db, user, tid)  # quyền đọc lại ở mỗi request (FR-AUTH-04)
        if ctx.role != "partner" or ctx.pack != "agency":
            continue
        try:
            month = query(
                ctx,
                QueryIn(metrics=["ad_spend", "roas_blended"], time={"preset": "this_month"}),
                db=db,
                caller="partner",
            )
            pacing = query(
                ctx, QueryIn(metrics=["budget_pacing"], time={"preset": "this_month"}), db=db, caller="partner"
            )
            row = month["rows"][0] if month["rows"] else {}
            prow = pacing["rows"][0] if pacing["rows"] else {}
            out.append(
                PartnerTenant(
                    tenant_id=tid,
                    name=t.name,
                    pack=t.pack,
                    ad_spend_mtd=row.get("ad_spend"),
                    budget_pacing=prow.get("budget_pacing"),
                    roas_blended=row.get("roas_blended"),
                    flags=compute_flags(ctx, db=db),
                    data_as_of=month["data_as_of"],
                )
            )
        except ApiError as exc:  # một khách lỗi không làm hỏng cả trang
            log.warning("partner: khách %s lỗi %s", tid, exc.code)
            out.append(
                PartnerTenant(
                    tenant_id=tid,
                    name=t.name,
                    pack=t.pack,
                    ad_spend_mtd=None,
                    budget_pacing=None,
                    roas_blended=None,
                    flags=[],
                    data_as_of=None,
                    error=exc.detail,
                )
            )
    out.sort(key=lambda r: (-len(r.flags), -(r.ad_spend_mtd or 0)))
    return out
