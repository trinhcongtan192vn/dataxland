"""Kiểm tra sức khỏe dữ liệu (spec 07 §9).

Công khai: gửi file, xác nhận email, xem kết quả đã duyệt, đồng ý chuyển dữ liệu.
Vận hành (`healthchecks.review`): danh sách, chi tiết, ghi chú, duyệt và gửi, chuyển thành khách.
Nội bộ (Dagster): bắt đầu, cập nhật file, lỗi, dựng kết quả, danh sách hết hạn, đánh dấu đã xóa.
"""

from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.context import CurrentUser, get_current_user
from app.auth.internal import ServiceCaller, require_service
from app.db import get_db
from app.db.models import HealthCheck, HealthCheckFile
from app.errors import ApiError
from app.healthchecks.result import build_result, public_view
from app.healthchecks.tenant import KIND_FILE_SOURCE, KIND_SOURCE, pii_salt, save_file
from app.metrics.registry import repo_root
from app.notify.direct import send_email_now
from app.notify.types import Button
from app.ratelimit import check_key_rate
from app.routers.ops import require_staff
from dx_common.config import get_settings
from dx_common.events import publish
from dx_common.ids import new_ulid, random_token
from dx_common.timeutil import now_utc

router = APIRouter(tags=["health_checks"])

KINDS = tuple(KIND_FILE_SOURCE)
MAX_FILES, MAX_BYTES = 10, 20 * 1024 * 1024
RETENTION = timedelta(days=14)
MIN_FILL_SECONDS = 3
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
STATUS_VI = {
    "uploaded": "Chờ xác nhận email",
    "verified": "Đã xác nhận, chờ xử lý",
    "processing": "Đang xử lý",
    "ready_for_review": "Chờ duyệt",
    "approved": "Đã gửi kết quả",
    "failed": "Lỗi",
    "expired": "Đã xóa",
    "converted": "Đã chuyển thành khách",
}


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def consent() -> dict[str, str]:
    """Văn bản đồng ý (NFR-11) và phiên bản, đọc từ `knowledge/legal/health-check-consent.md`."""
    raw = (Path(repo_root()) / "knowledge" / "legal" / "health-check-consent.md").read_text(encoding="utf-8")
    meta, _, body = raw.removeprefix("---\n").partition("\n---\n")
    return {"version": str(yaml.safe_load(meta)["version"]), "text_md": body.strip()}


def _base() -> str:
    return get_settings().dx_public_base_url.rstrip("/")


def _get(db: Session, check_id: str) -> HealthCheck:
    hc = db.get(HealthCheck, check_id)
    if hc is None:
        raise ApiError(404, "HEALTHCHECK_NOT_FOUND", "Không tìm thấy lượt kiểm tra")
    return hc


# --------------------------------------------------------------------------- công khai


@router.get("/v1/health-checks/consent")
def get_consent() -> dict[str, Any]:
    labels = {k: v for k, v in _kind_labels().items()}
    return {
        **consent(),
        "kinds": labels,
        "max_files": MAX_FILES,
        "max_mb": MAX_BYTES // (1024 * 1024),
        "retention_days": RETENTION.days,
    }


def _kind_labels() -> dict[str, str]:
    return {
        "shopee_orders": "Shopee – Đơn hàng",
        "shopee_income": "Shopee – Báo cáo doanh thu",
        "tiktok_shop_orders": "TikTok Shop – Đơn hàng",
        "tiktok_shop_settlement": "TikTok Shop – Báo cáo quyết toán",
        "lazada_orders": "Lazada – Đơn hàng",
        "lazada_transactions": "Lazada – Báo cáo giao dịch",
        "meta_ads": "Meta Ads – Báo cáo theo ngày",
        "tiktok_ads": "TikTok Ads – Báo cáo theo ngày",
        "google_ads": "Google Ads – Báo cáo theo ngày",
        "product_costs": "Giá vốn (mẫu DataxLand)",
    }


@router.post("/v1/health-checks", status_code=202)
async def submit(
    request: Request,
    email: str = Form(...),
    consent_version: str = Form(...),
    kinds: list[str] = Form(...),
    files: list[UploadFile] = File(...),
    shop_name: str | None = Form(default=None),
    website: str | None = Form(default=None),  # honeypot: người thật không điền
    started_at: int | None = Form(default=None),  # ms epoch lúc mở biểu mẫu
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ip = request.client.host if request.client else "unknown"
    ip_hash = _h(f"hc-ip:{ip}")
    check_key_rate(db, f"hc:{ip_hash}", 5, 3600)
    if website:
        raise ApiError(400, "REJECTED", "Không gửi được biểu mẫu")
    if started_at is not None and time.time() - started_at / 1000 < MIN_FILL_SECONDS:
        raise ApiError(400, "TOO_FAST", "Biểu mẫu được gửi quá nhanh, thử lại")
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ApiError(422, "EMAIL_INVALID", "Email không hợp lệ")
    c = consent()
    if consent_version != c["version"]:
        raise ApiError(422, "CONSENT_OUTDATED", "Văn bản đồng ý đã đổi, vui lòng tải lại trang")
    if not files or len(files) > MAX_FILES or len(kinds) != len(files):
        raise ApiError(422, "FILES_INVALID", f"Gửi từ 1 đến {MAX_FILES} file, mỗi file chọn một loại")
    contents: list[tuple[UploadFile, str, bytes]] = []
    for f, k in zip(files, kinds, strict=True):
        name = (f.filename or "file").rsplit("/", 1)[-1][:200]
        if k not in KINDS:
            raise ApiError(422, "KIND_INVALID", f"Loại file không hợp lệ: {k}")
        if not name.lower().endswith((".xlsx", ".csv")):
            raise ApiError(422, "EXTENSION", f"{name}: chỉ nhận .xlsx hoặc .csv")
        data = await f.read()
        if len(data) > MAX_BYTES:
            raise ApiError(422, "FILE_TOO_LARGE", f"{name}: vượt 20 MB")
        if not data:
            raise ApiError(422, "FILE_EMPTY", f"{name}: file trống")
        contents.append((f, k, data))
    now = now_utc()
    check_id = new_ulid().lower()
    token = random_token(24)
    hc = HealthCheck(
        check_id=check_id,
        email=email,
        shop_name=(shop_name or "").strip()[:120] or None,
        status="uploaded",
        consent_version=c["version"],
        consent_at=now,
        email_token_hash=_h(token),
        expires_at=now + RETENTION,
        ip_hash=ip_hash,
    )
    db.add(hc)
    db.flush()
    for f, k, data in contents:
        fid = new_ulid().lower()
        path = save_file(check_id, fid, data)
        db.add(
            HealthCheckFile(
                id=fid,
                check_id=check_id,
                declared_kind=k,
                filename=(f.filename or "file").rsplit("/", 1)[-1][:200],
                size_bytes=len(data),
                gcs_path=path,
                status="received",
            )
        )
    audit(db, action="healthcheck.uploaded", target=check_id, actor_service="public", detail={"files": len(contents)})
    url = f"{_base()}/health-check/verify?token={token}"
    send_email_now(
        email,
        "healthcheck_verify",
        {"shop_name": hc.shop_name, "verify_url": url, "expires_on": hc.expires_at.date()},
        [Button("Xác nhận", url)],
    )
    return {"check_id": check_id, "expires_at": hc.expires_at.isoformat()}


@router.get("/v1/health-checks/verify")
def verify(token: str = Query(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    hc = db.scalar(select(HealthCheck).where(HealthCheck.email_token_hash == _h(token)))
    if hc is None:
        raise ApiError(404, "TOKEN_INVALID", "Link xác nhận không đúng hoặc đã hết hạn")
    if hc.status == "uploaded":
        hc.status, hc.email_verified_at = "verified", now_utc()
        db.flush()
        publish("healthcheck.submitted", None, {"check_id": hc.check_id}, "s5-healthcheck", bind=db)
        audit(db, action="healthcheck.verified", target=hc.check_id, actor_service="public")
    return {"check_id": hc.check_id, "status": hc.status, "expires_at": hc.expires_at.isoformat()}


def _by_access(db: Session, check_id: str, k: str) -> HealthCheck:
    hc = db.get(HealthCheck, check_id)
    if hc is None or hc.status != "approved" or not hc.access_token_hash or _h(k) != hc.access_token_hash:
        raise ApiError(404, "RESULT_NOT_FOUND", "Không tìm thấy kết quả")
    return hc


@router.get("/v1/health-checks/{check_id}/result")
def public_result(check_id: str, k: str = Query(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    hc = _by_access(db, check_id, k)
    return {
        "check_id": hc.check_id,
        "shop_name": hc.shop_name,
        "result": public_view(hc.result),
        "reviewer_notes_md": hc.reviewer_notes_md,
        "approved_at": hc.approved_at,
        "expires_at": hc.expires_at,
        "consent_convert_at": hc.consent_convert_at,
    }


@router.post("/v1/health-checks/{check_id}/consent-convert")
def consent_convert(check_id: str, k: str = Query(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    hc = _by_access(db, check_id, k)
    hc.consent_convert_at = hc.consent_convert_at or now_utc()
    audit(db, action="healthcheck.consent_convert", target=check_id, actor_service="public")
    return {"consent_convert_at": hc.consent_convert_at}


# --------------------------------------------------------------------------- vận hành


class HcSummary(BaseModel):
    check_id: str
    email: str
    shop_name: str | None
    status: str
    status_vi: str
    created_at: datetime
    expires_at: datetime
    files: int
    files_rejected: int


class HcDetail(HcSummary):
    result: dict[str, Any] | None
    reviewer_notes_md: str | None
    approved_at: datetime | None
    consent_convert_at: datetime | None
    converted_tenant_id: str | None
    file_list: list[dict[str, Any]]


def _summary(db: Session, hc: HealthCheck) -> dict[str, Any]:
    n = db.scalar(select(func.count()).select_from(HealthCheckFile).where(HealthCheckFile.check_id == hc.check_id))
    rej = db.scalar(
        select(func.count())
        .select_from(HealthCheckFile)
        .where(HealthCheckFile.check_id == hc.check_id, HealthCheckFile.status == "rejected")
    )
    return {
        "check_id": hc.check_id,
        "email": hc.email,
        "shop_name": hc.shop_name,
        "status": hc.status,
        "status_vi": STATUS_VI.get(hc.status, hc.status),
        "created_at": hc.created_at,
        "expires_at": hc.expires_at,
        "files": int(n or 0),
        "files_rejected": int(rej or 0),
    }


@router.get("/v1/ops/health-checks", response_model=list[HcSummary])
def ops_list(
    status: str | None = None, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    require_staff(user, "healthchecks.review")
    q = select(HealthCheck)
    if status:
        q = q.where(HealthCheck.status == status)
    return [_summary(db, hc) for hc in db.scalars(q.order_by(HealthCheck.created_at.desc()).limit(300))]


def _detail(db: Session, hc: HealthCheck) -> HcDetail:
    files = db.scalars(
        select(HealthCheckFile).where(HealthCheckFile.check_id == hc.check_id).order_by(HealthCheckFile.created_at)
    )
    return HcDetail(
        **_summary(db, hc),
        result=hc.result,
        reviewer_notes_md=hc.reviewer_notes_md,
        approved_at=hc.approved_at,
        consent_convert_at=hc.consent_convert_at,
        converted_tenant_id=hc.converted_tenant_id,
        file_list=[
            {
                "id": f.id,
                "filename": f.filename,
                "declared_kind": f.declared_kind,
                "detected_kind": f.detected_kind,
                "status": f.status,
                "size_bytes": f.size_bytes,
                "error_message_vi": f.error_message_vi,
                "rows_loaded": f.rows_loaded,
                "date_from": f.date_from,
                "date_to": f.date_to,
            }
            for f in files
        ],
    )


@router.get("/v1/ops/health-checks/{check_id}", response_model=HcDetail)
def ops_detail(check_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> HcDetail:
    require_staff(user, "healthchecks.review")
    return _detail(db, _get(db, check_id))


class NotesIn(BaseModel):
    reviewer_notes_md: str = Field(max_length=4000)


@router.put("/v1/ops/health-checks/{check_id}", response_model=HcDetail)
def ops_notes(
    check_id: str, body: NotesIn, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> HcDetail:
    require_staff(user, "healthchecks.review")
    hc = _get(db, check_id)
    if hc.status not in ("ready_for_review", "approved"):
        raise ApiError(409, "HEALTHCHECK_NOT_READY", "Lượt kiểm tra chưa có kết quả")
    hc.reviewer_notes_md = body.reviewer_notes_md.strip() or None
    audit(db, action="healthcheck.notes", target=check_id, actor_user_id=user.id)
    return _detail(db, hc)


@router.post("/v1/ops/health-checks/{check_id}/approve")
def ops_approve(
    check_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict[str, Any]:
    require_staff(user, "healthchecks.review")
    hc = _get(db, check_id)
    if hc.status != "ready_for_review":
        raise ApiError(409, "HEALTHCHECK_NOT_READY", "Chỉ duyệt được lượt đang chờ duyệt")
    token = random_token(24)
    hc.access_token_hash, hc.status = _h(token), "approved"
    hc.reviewed_by, hc.approved_at = user.id, now_utc()
    url = f"{_base()}/health-check/{check_id}?k={token}"
    res = send_email_now(
        hc.email,
        "healthcheck_ready",
        {"shop_name": hc.shop_name, "result_url": url, "expires_on": hc.expires_at.date()},
        [Button("Xem kết quả", url)],
    )
    audit(db, action="healthcheck.approved", target=check_id, actor_user_id=user.id, detail={"email_sent": res.ok})
    return {"status": hc.status, "email_sent": res.ok, "result_url": url}


class ConvertIn(BaseModel):
    tenant_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,30}$")
    pack: str = Field(pattern=r"^(seller|agency)$")
    name: str | None = None


@router.post("/v1/ops/health-checks/{check_id}/convert")
def ops_convert(
    check_id: str, body: ConvertIn, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Sinh bản nháp `tenants/<id>.yml` từ loại file (spec 07 §8). Data lead mở PR với nội dung này."""
    require_staff(user, "healthchecks.review")
    hc = _get(db, check_id)
    if hc.status in ("expired", "uploaded"):
        raise ApiError(409, "HEALTHCHECK_NOT_CONVERTIBLE", "Lượt kiểm tra đã xóa hoặc chưa xác nhận")
    draft = convert_draft(db, hc, body.tenant_id, body.pack, body.name)
    hc.status, hc.converted_tenant_id = "converted", body.tenant_id
    audit(
        db,
        action="healthcheck.converted",
        target=check_id,
        actor_user_id=user.id,
        detail={"tenant_id": body.tenant_id, "copy_raw": bool(hc.consent_convert_at)},
    )
    return {"tenant_id": body.tenant_id, "yaml": draft, "copy_raw_allowed": hc.consent_convert_at is not None}


def convert_draft(db: Session, hc: HealthCheck, tenant_id: str, pack: str, name: str | None) -> str:
    import tempfile

    from dx_common.tenants.validate import TenantValidationError, load_tenant_file

    kinds = sorted(
        {
            f.declared_kind
            for f in db.scalars(
                select(HealthCheckFile).where(
                    HealthCheckFile.check_id == hc.check_id, HealthCheckFile.status == "loaded"
                )
            )
        }
    )
    types = sorted({KIND_SOURCE[k] for k in kinds if k in KIND_SOURCE})
    sources: list[dict[str, Any]] = []
    for t in types:
        if t in ("meta_ads", "tiktok_ads", "google_ads"):
            sources.append({"type": t, "connector": "windsor", "account_id": "<điền account_id>"})
        else:
            sources.append(
                {
                    "type": t,
                    "connector": "dlt",
                    "account_id": "<điền shop_id>",
                    "secret_ref": f"dx-{tenant_id}-{t}-<shop_id>",
                }
            )
    if pack == "agency" and not any(s["type"] in ("meta_ads", "tiktok_ads", "google_ads") for s in sources):
        sources.append({"type": "meta_ads", "connector": "windsor", "account_id": "<điền account_id>"})
    doc = {
        "tenant_id": tenant_id,
        "name": name or hc.shop_name or tenant_id,
        "status": "active",
        "pack": pack,
        "sources": sources,
        "notify": {"email": [hc.email]},
    }
    text = "# Bản nháp sinh từ kiểm tra sức khỏe " + hc.check_id + " (spec 07 §8). Điền account_id rồi mở PR.\n"
    text += yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)
    with tempfile.TemporaryDirectory() as d:  # kiểm như CI kiểm `tenants/*.yml` (FR-HC-05)
        path = Path(d) / f"{tenant_id}.yml"
        path.write_text(text, encoding="utf-8")
        try:
            load_tenant_file(path)
        except TenantValidationError as exc:
            raise ApiError(422, "DRAFT_INVALID", "; ".join(exc.errors)[:500]) from exc
    return text


# --------------------------------------------------------------------------- nội bộ (Dagster)


@router.post("/v1/internal/health-checks/{check_id}/start")
def internal_start(
    check_id: str, _: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)
) -> dict[str, Any]:
    hc = _get(db, check_id)
    if hc.status not in ("verified", "processing", "failed"):
        raise ApiError(409, "HEALTHCHECK_NOT_VERIFIED", "Lượt kiểm tra chưa xác nhận email")
    hc.status = "processing"
    files = db.scalars(select(HealthCheckFile).where(HealthCheckFile.check_id == check_id))
    return {
        "check_id": check_id,
        "salt": pii_salt(check_id),
        "expires_at": hc.expires_at.isoformat(),
        "files": [
            {"id": f.id, "declared_kind": f.declared_kind, "filename": f.filename, "path": f.gcs_path} for f in files
        ],
    }


class FileStatusIn(BaseModel):
    files: list[dict[str, Any]]


@router.post("/v1/internal/health-checks/{check_id}/files")
def internal_files(
    check_id: str, body: FileStatusIn, _: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)
) -> dict[str, int]:
    from datetime import date as _date

    _get(db, check_id)
    n = 0
    for st in body.files:
        f = db.get(HealthCheckFile, st.get("id"))
        if f is None or f.check_id != check_id:
            continue
        f.status = st.get("status", f.status)
        f.detected_kind = st.get("detected_kind")
        f.error_code, f.error_message_vi = st.get("error_code"), st.get("error_message_vi")
        f.rows_loaded = st.get("rows_loaded")
        f.date_from = _date.fromisoformat(st["date_from"]) if st.get("date_from") else None
        f.date_to = _date.fromisoformat(st["date_to"]) if st.get("date_to") else None
        n += 1
    return {"updated": n}


class FailIn(BaseModel):
    reason: str


@router.post("/v1/internal/health-checks/{check_id}/fail")
def internal_fail(
    check_id: str, body: FailIn, _: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)
) -> dict[str, str]:
    hc = _get(db, check_id)
    hc.status = "failed"
    publish("healthcheck.failed", None, {"check_id": check_id}, "s5-healthcheck", bind=db)
    audit(db, action="healthcheck.failed", target=check_id, actor_service="dagster", detail={"reason": body.reason})
    return {"status": "failed"}


class BuildHcIn(BaseModel):
    mapping_issues: list[str] = Field(default_factory=list)
    file_ranges: dict[str, Any] = Field(default_factory=dict)


@router.post("/v1/internal/health-checks/{check_id}/build")
def internal_build(
    check_id: str, body: BuildHcIn, _: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)
) -> dict[str, Any]:
    hc = _get(db, check_id)
    hc.result = build_result(db, hc, body.mapping_issues)
    hc.status = "ready_for_review"
    db.flush()
    publish("healthcheck.completed", None, {"check_id": check_id}, "s5-healthcheck", bind=db)
    audit(db, action="healthcheck.built", target=check_id, actor_service="dagster")
    return {"status": hc.status}


@router.post("/v1/internal/health-checks/expired")
def internal_expired(_: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Lượt quá hạn, chưa chuyển đổi, chưa xóa (spec 07 §7)."""
    rows = db.scalars(
        select(HealthCheck).where(
            HealthCheck.expires_at < now_utc(), HealthCheck.deleted_at.is_(None), HealthCheck.status != "converted"
        )
    )
    return {"items": [{"check_id": h.check_id} for h in rows]}


class ExpiredIn(BaseModel):
    tables: int = 0
    files: int = 0


@router.post("/v1/internal/health-checks/{check_id}/expired")
def internal_mark_expired(
    check_id: str, body: ExpiredIn, _: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)
) -> dict[str, str]:
    hc = _get(db, check_id)
    if hc.status == "converted":
        raise ApiError(409, "HEALTHCHECK_CONVERTED", "Lượt đã chuyển thành khách, không xóa ở đây")
    files = list(db.scalars(select(HealthCheckFile).where(HealthCheckFile.check_id == check_id)))
    hc.funnel_counts = {
        "files": len(files),
        "had_result": hc.result is not None,
        "approved": hc.approved_at is not None,
    }
    hc.result, hc.status, hc.deleted_at = None, "expired", now_utc()
    for f in files:
        f.gcs_path = None
    audit(
        db,
        action="healthcheck.deleted",
        target=check_id,
        actor_service="dagster",
        detail={"tables": body.tables, "files": body.files},
    )
    return {"status": "expired"}


@router.post("/v1/internal/health-checks/{check_id}/convert-info")
def internal_convert_info(
    check_id: str, _: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)
) -> dict[str, Any]:
    hc = _get(db, check_id)
    return {
        "tenant_id": hc.converted_tenant_id,
        "copy_raw_allowed": hc.status == "converted" and hc.consent_convert_at is not None,
    }


class PurgedIn(BaseModel):
    tables: int = 0
    files: int = 0
    copied: list[str] = Field(default_factory=list)


@router.post("/v1/internal/health-checks/{check_id}/purged")
def internal_purged(
    check_id: str, body: PurgedIn, _: ServiceCaller = Depends(require_service), db: Session = Depends(get_db)
) -> dict[str, str]:
    """Dữ liệu tạm của lượt đã chuyển đổi đã được sao chép sang khách mới và xóa (spec 07 §8 bước 2)."""
    hc = _get(db, check_id)
    hc.result, hc.deleted_at = None, now_utc()
    audit(
        db,
        action="healthcheck.purged_after_convert",
        target=check_id,
        actor_service="dagster",
        detail={"tables": body.tables, "files": body.files, "copied": body.copied[:50]},
    )
    return {"status": hc.status}
