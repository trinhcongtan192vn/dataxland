"""Cấu hình "khách tạm" của lượt kiểm tra (spec 07 §5): gói Seller, nguồn theo các file đã nạp."""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import HealthCheck, HealthCheckFile
from app.errors import ApiError
from dx_common.config import get_settings
from dx_common.tenants import TenantConfig

# Loại file → nguồn tương ứng (để quy tắc `requires` của chỉ số và gói quảng cáo áp dụng như khách thật).
KIND_SOURCE = {
    "shopee_orders": "shopee",
    "shopee_income": "shopee",
    "tiktok_shop_orders": "tiktok_shop",
    "tiktok_shop_settlement": "tiktok_shop",
    "lazada_orders": "lazada",
    "lazada_transactions": "lazada",
    "meta_ads": "meta_ads",
    "tiktok_ads": "tiktok_ads",
    "google_ads": "google_ads",
}
KIND_FILE_SOURCE = {
    "shopee_orders": "shopee_file",
    "shopee_income": "shopee_file",
    "tiktok_shop_orders": "tiktok_shop_file",
    "tiktok_shop_settlement": "tiktok_shop_file",
    "lazada_orders": "lazada_file",
    "lazada_transactions": "lazada_file",
    "meta_ads": "meta_ads_file",
    "tiktok_ads": "tiktok_ads_file",
    "google_ads": "google_ads_file",
    "product_costs": "portal_file",
}


def check_id_of(tenant_id: str) -> str:
    return tenant_id.removeprefix("hc_")


def tenant_id_of(check_id: str) -> str:
    return f"hc_{check_id}"


def pii_salt(check_id: str) -> str:
    """Muối tạm của lượt kiểm tra (spec 07 §4.2): tất định theo `check_id`, không lưu ở đâu."""
    key = (get_settings().internal_api_token or "dx-local").encode()
    return hmac.new(key, f"hc-salt:{check_id}".encode(), hashlib.sha256).hexdigest()


def loaded_kinds(db: Session, check_id: str) -> list[str]:
    rows = db.scalars(
        select(HealthCheckFile.declared_kind).where(
            HealthCheckFile.check_id == check_id, HealthCheckFile.status == "loaded"
        )
    )
    return sorted(set(rows))


def healthcheck_tenant_config(db: Session, tenant_id: str) -> TenantConfig:
    check_id = check_id_of(tenant_id)
    hc = db.get(HealthCheck, check_id)
    if hc is None:
        raise ApiError(404, "HEALTHCHECK_NOT_FOUND", "Không tìm thấy lượt kiểm tra")
    types = sorted({KIND_SOURCE[k] for k in loaded_kinds(db, check_id) if k in KIND_SOURCE})
    sources = [{"type": t, "connector": "dlt", "account_id": "file", "secret_ref": "none"} for t in types]
    return TenantConfig.model_validate(
        {
            "tenant_id": tenant_id,
            "name": hc.shop_name or f"Kiểm tra {check_id[:8]}",
            "pack": "seller",
            "sources": sources,
            "cost_allocation": "by_revenue",
            "quality": {"freshness_hours": 24 * 365},
        }
    )


def storage_root() -> str:
    return get_settings().hc_bucket.rstrip("/")


def save_file(check_id: str, file_id: str, content: bytes) -> str:
    """Lưu file gốc ở `<HC_BUCKET>/<check_id>/<file_id>` (GCS hoặc thư mục local); bucket có lifecycle 15 ngày."""
    root = storage_root()
    if root.startswith("gs://"):  # pragma: no cover - cần GCS
        import google.cloud.storage as storage

        bucket, _, prefix = root[5:].partition("/")
        name = "/".join(x for x in (prefix, check_id, file_id) if x)
        storage.Client().bucket(bucket).blob(name).upload_from_string(content)
        return f"gs://{bucket}/{name}"
    path = Path(root) / check_id / file_id
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return str(path.resolve())
