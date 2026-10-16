"""Quy ước tên theo khách (spec 00 §3.1, spec 04 §2)."""

from __future__ import annotations

import hashlib

LAYERS = ("raw", "stg", "core", "marts")


def dataset_prefix(tenant_id: str) -> str:
    return f"t_{tenant_id}" if not tenant_id.startswith("hc_") else tenant_id


def datasets(tenant_id: str) -> list[str]:
    p = dataset_prefix(tenant_id)
    return [f"{p}_{layer}" for layer in LAYERS]


def service_account_id(tenant_id: str) -> str:
    """`dxt-<slug>`: `_` → `-`, cắt cho đủ 30 ký tự, thêm 4 ký tự hash nếu bị cắt (spec 04 §2 bước 3)."""
    slug = tenant_id.replace("_", "-")
    full = f"dxt-{slug}"
    if len(full) <= 30:
        return full
    h = hashlib.sha256(tenant_id.encode()).hexdigest()[:4]
    return f"{full[:25]}-{h}"


def pii_salt_secret(tenant_id: str) -> str:
    return f"dx-{tenant_id}-pii-salt"


def source_secret(tenant_id: str, source: str, account_id: str) -> str:
    """Tên secret token gian hàng: `dx-<tenant_id>-<source>-<account_id>` (spec 05 §6.7)."""
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in account_id)
    return f"dx-{tenant_id}-{source}-{safe}"


def app_secret(source: str) -> str:
    """Khóa ứng dụng đối tác dùng chung: `dx-<source>-app` (spec 01 §2.2)."""
    return f"dx-{source}-app"
