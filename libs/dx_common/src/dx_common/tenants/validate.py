"""Đọc và kiểm tra thư mục `tenants/` (spec 04 §1.1, §1.2)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from dx_common.tenants.models import Partner, TenantConfig

_FORBIDDEN_KEY_RE = re.compile(r"(token|key|password|secret)", re.IGNORECASE)


class TenantValidationError(ValueError):
    def __init__(self, path: str, errors: list[str]) -> None:
        self.path = path
        self.errors = errors
        super().__init__(f"{path}: " + "; ".join(errors))


def _scan_forbidden_keys(node: Any, trail: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            key = str(k)
            here = f"{trail}.{key}" if trail else key
            if key != "secret_ref" and _FORBIDDEN_KEY_RE.search(key):
                found.append(f"trường cấm chứa bí mật: {here}")
            found.extend(_scan_forbidden_keys(v, here))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            found.extend(_scan_forbidden_keys(v, f"{trail}[{i}]"))
    return found


def load_partners(tenants_dir: str | Path) -> dict[str, Partner]:
    p = Path(tenants_dir) / "partners.yml"
    if not p.exists():
        return {}
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    items = raw.get("partners", raw) if isinstance(raw, dict) else raw
    out: dict[str, Partner] = {}
    for item in items or []:
        partner = Partner.model_validate(item)
        out[partner.partner_id] = partner
    return out


def load_tenant_file(path: str | Path, partner_ids: set[str] | None = None) -> TenantConfig:
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise TenantValidationError(str(p), [f"YAML lỗi: {exc}"]) from exc
    if not isinstance(raw, dict):
        raise TenantValidationError(str(p), ["file phải là một object YAML"])
    errors = _scan_forbidden_keys(raw)
    try:
        cfg = TenantConfig.model_validate(raw)
    except ValidationError as exc:
        errors.extend(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors())
        raise TenantValidationError(str(p), errors) from exc
    if cfg.tenant_id != p.stem:
        errors.append(f"tenant_id '{cfg.tenant_id}' không trùng tên file '{p.stem}'")
    if partner_ids is not None:
        unknown = [x for x in cfg.partners if x not in partner_ids]
        if unknown:
            errors.append(f"partners không có trong partners.yml: {', '.join(unknown)}")
    if errors:
        raise TenantValidationError(str(p), errors)
    return cfg


def tenant_files(tenants_dir: str | Path) -> list[Path]:
    root = Path(tenants_dir)
    return sorted(p for p in root.glob("*.yml") if p.name != "partners.yml")


def validate_dir(tenants_dir: str | Path) -> tuple[dict[str, TenantConfig], list[TenantValidationError]]:
    """Trả (khách hợp lệ, lỗi). File lỗi không làm hỏng file khác (spec 04 §1.3)."""
    partners = load_partners(tenants_dir)
    ok: dict[str, TenantConfig] = {}
    errs: list[TenantValidationError] = []
    for f in tenant_files(tenants_dir):
        try:
            cfg = load_tenant_file(f, set(partners))
            ok[cfg.tenant_id] = cfg
        except TenantValidationError as exc:
            errs.append(exc)
    return ok, errs
