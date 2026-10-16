"""Sổ đăng ký khách: model, đọc và kiểm tra file `tenants/<tenant_id>.yml` (spec 04 §1)."""

from dx_common.tenants.models import (
    AD_SOURCES,
    AMAZON_SOURCES,
    SALES_SOURCES,
    Partner,
    SourceConfig,
    TenantConfig,
)
from dx_common.tenants.validate import (
    TenantValidationError,
    load_partners,
    load_tenant_file,
    validate_dir,
)

__all__ = [
    "AD_SOURCES",
    "AMAZON_SOURCES",
    "SALES_SOURCES",
    "Partner",
    "SourceConfig",
    "TenantConfig",
    "TenantValidationError",
    "load_partners",
    "load_tenant_file",
    "validate_dir",
]
