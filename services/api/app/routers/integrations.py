"""Trạng thái cấu hình tích hợp và hướng dẫn lấy khóa (ADR 0001).

- `GET /v1/ops/integrations`: mỗi nền tảng một dòng, chỉ trả "đã cấu hình / chưa cấu hình" cho từng biến hoặc secret,
  không bao giờ trả giá trị (spec 00 §3.4, §3.5).
- `GET /v1/ops/integrations/{key}`: như trên kèm nội dung hướng dẫn `knowledge/integrations/<key>.md` và trạng thái
  kết nối của từng khách dùng nền tảng đó.

Quyền: `ops.read` (nhân viên DataxLand).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.context import CurrentUser, get_current_user
from app.db import get_db
from app.db.models import SourceSync, Tenant
from app.errors import ApiError
from app.metrics.registry import repo_root
from app.routers.ops import require_staff
from dx_common.config import Settings, get_settings
from dx_common.secrets import get_secret_store
from dx_common.tenants import TenantConfig
from dx_common.tenants.naming import app_secret, source_secret

router = APIRouter(prefix="/v1/ops/integrations", tags=["integrations"])


@dataclass(frozen=True)
class Check:
    label_vi: str
    kind: Literal["env", "secret", "web_env"]
    name: str
    required: bool = True


@dataclass(frozen=True)
class Platform:
    key: str
    name_vi: str
    category: Literal["marketplace", "ads", "messaging", "auth", "email", "reference", "ai", "warehouse"]
    checks: tuple[Check, ...]
    sources: tuple[str, ...] = ()  # loại nguồn trong `tenants/*.yml` dùng nền tảng này


PLATFORMS: tuple[Platform, ...] = (
    Platform(
        "shopee",
        "Shopee Open Platform",
        "marketplace",
        (
            Check("Khóa ứng dụng đối tác (partner_id, partner_key)", "secret", app_secret("shopee")),
            Check("URL công khai của API cho callback OAuth", "env", "MARKETPLACE_OAUTH_REDIRECT_BASE"),
        ),
        ("shopee",),
    ),
    Platform(
        "tiktok_shop",
        "TikTok Shop Partner Center",
        "marketplace",
        (
            Check("Khóa ứng dụng (app_key, app_secret, service_id)", "secret", app_secret("tiktok_shop")),
            Check("URL công khai của API cho callback OAuth", "env", "MARKETPLACE_OAUTH_REDIRECT_BASE"),
        ),
        ("tiktok_shop",),
    ),
    Platform(
        "lazada",
        "Lazada Open Platform",
        "marketplace",
        (
            Check("Khóa ứng dụng (app_key, app_secret)", "secret", app_secret("lazada")),
            Check("URL công khai của API cho callback OAuth", "env", "MARKETPLACE_OAUTH_REDIRECT_BASE"),
        ),
        ("lazada",),
    ),
    Platform(
        "windsor",
        "Windsor.ai (Meta, TikTok, Google, Amazon Ads; Amazon Seller)",
        "ads",
        (Check("Khóa API Windsor (chỉ để kiểm tra trạng thái)", "env", "WINDSOR_API_KEY", required=False),),
        ("meta_ads", "tiktok_ads", "google_ads", "amazon_ads", "amazon_seller"),
    ),
    Platform(
        "telegram",
        "Telegram Bot",
        "messaging",
        (
            Check("Token bot từ BotFather", "env", "TELEGRAM_BOT_TOKEN"),
            Check("Tên bot (không có @)", "env", "TELEGRAM_BOT_USERNAME"),
            Check("Secret xác thực webhook", "env", "TELEGRAM_WEBHOOK_SECRET"),
            Check("Chat ID nhóm cảnh báo của team", "env", "TELEGRAM_TEAM_CHAT_ID"),
            Check("URL công khai của bot (chế độ webhook)", "env", "BOT_PUBLIC_URL", required=False),
        ),
    ),
    Platform(
        "firebase",
        "Firebase Authentication",
        "auth",
        (
            Check("Project ID", "env", "FIREBASE_PROJECT_ID"),
            Check(
                "Cấu hình web (NEXT_PUBLIC_FIREBASE_API_KEY, AUTH_DOMAIN, PROJECT_ID)",
                "web_env",
                "NEXT_PUBLIC_FIREBASE_*",
                required=False,
            ),
        ),
    ),
    Platform(
        "smtp",
        "Email (SMTP)",
        "email",
        (
            Check("Máy chủ SMTP", "env", "SMTP_HOST"),
            Check("Tài khoản SMTP", "env", "SMTP_USER", required=False),
            Check("Mật khẩu SMTP", "env", "SMTP_PASSWORD", required=False),
            Check("Địa chỉ gửi", "env", "EMAIL_FROM"),
            Check("Email nhận cảnh báo của team", "env", "DX_TEAM_EMAIL"),
        ),
    ),
    Platform(
        "fx_vcb",
        "Tỷ giá Vietcombank",
        "reference",
        (
            Check("URL dữ liệu tỷ giá", "env", "FX_VCB_URL"),
            Check("Danh sách ngoại tệ", "env", "FX_CURRENCIES"),
        ),
    ),
    Platform(
        "bigquery",
        "Google Cloud (BigQuery, Secret Manager)",
        "warehouse",
        (
            Check("GCP project", "env", "GCP_PROJECT_ID"),
            Check("Vùng BigQuery", "env", "BQ_LOCATION"),
        ),
    ),
    Platform(
        "anthropic",
        "Anthropic (lớp AI, giai đoạn 2)",
        "ai",
        (Check("Khóa API Anthropic", "env", "ANTHROPIC_API_KEY", required=False),),
    ),
)
BY_KEY = {p.key: p for p in PLATFORMS}
LOCAL_OK = {"GCP_PROJECT_ID", "BQ_LOCATION", "FIREBASE_PROJECT_ID"}  # ở local không bắt buộc


class CheckOut(BaseModel):
    label_vi: str
    kind: str
    name: str
    required: bool
    configured: bool | None  # None: không kiểm được từ API (biến của web)


class TenantSourceOut(BaseModel):
    tenant_id: str
    tenant_name: str
    source: str
    account_id: str
    connector: str
    secret_ref: str | None
    secret_configured: bool | None
    connected_at: str | None
    last_status: str | None
    last_error_code: str | None


class IntegrationOut(BaseModel):
    key: str
    name_vi: str
    category: str
    guide_url: str
    ready: bool
    checks: list[CheckOut]
    tenants: list[TenantSourceOut] = []


class IntegrationDetail(IntegrationOut):
    guide_md: str


def _env_value(s: Settings, name: str) -> str:
    return str(getattr(s, name.lower(), "") or "")


def _status(p: Platform, s: Settings) -> list[CheckOut]:
    store = get_secret_store(s)
    out: list[CheckOut] = []
    for c in p.checks:
        configured: bool | None
        if c.kind == "secret":
            configured = store.exists(c.name)
        elif c.kind == "env":
            configured = bool(_env_value(s, c.name))
        else:
            configured = None
        required = c.required and not (s.is_local and c.name in LOCAL_OK)
        out.append(CheckOut(label_vi=c.label_vi, kind=c.kind, name=c.name, required=required, configured=configured))
    return out


def _tenants(p: Platform, db: Session, s: Settings) -> list[TenantSourceOut]:
    if not p.sources:
        return []
    store = get_secret_store(s)
    out: list[TenantSourceOut] = []
    for t in db.scalars(select(Tenant).where(Tenant.status != "archived").order_by(Tenant.tenant_id)):
        cfg = TenantConfig.model_validate(t.config)
        for src in cfg.sources:
            if src.type not in p.sources:
                continue
            acct = src.account_id or ""
            sync = db.scalar(
                select(SourceSync).where(
                    SourceSync.tenant_id == t.tenant_id, SourceSync.source == src.type, SourceSync.account_id == acct
                )
            )
            ref = src.secret_ref if src.connector == "dlt" else None
            if src.connector == "dlt" and not ref and acct:
                ref = source_secret(t.tenant_id, src.type, acct)
            out.append(
                TenantSourceOut(
                    tenant_id=t.tenant_id,
                    tenant_name=t.name,
                    source=src.type,
                    account_id=acct,
                    connector=src.connector,
                    secret_ref=ref,
                    secret_configured=store.exists(ref) if ref else None,
                    connected_at=sync.connected_at.isoformat() if sync and sync.connected_at else None,
                    last_status=sync.last_status if sync else None,
                    last_error_code=sync.last_error_code if sync else None,
                )
            )
    return out


def _row(p: Platform, db: Session, s: Settings) -> IntegrationOut:
    checks = _status(p, s)
    ready = all(c.configured for c in checks if c.required and c.configured is not None)
    return IntegrationOut(
        key=p.key,
        name_vi=p.name_vi,
        category=p.category,
        guide_url=f"/ops/integrations/{p.key}",
        ready=ready,
        checks=checks,
        tenants=_tenants(p, db, s),
    )


@router.get("", response_model=list[IntegrationOut])
def list_integrations(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Any]:
    require_staff(user, "ops.read")
    s = get_settings()
    return [_row(p, db, s) for p in PLATFORMS]


@router.get("/{key}", response_model=IntegrationDetail)
def get_integration(
    key: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> IntegrationDetail:
    require_staff(user, "ops.read")
    p = BY_KEY.get(key)
    if p is None:
        raise ApiError(404, "INTEGRATION_UNKNOWN", f"Không có hướng dẫn cho {key}")
    path = Path(repo_root()) / "knowledge" / "integrations" / f"{key}.md"
    md = path.read_text(encoding="utf-8") if path.exists() else ""
    return IntegrationDetail(**_row(p, db, get_settings()).model_dump(), guide_md=md)
