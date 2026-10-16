"""Đồng bộ `tenants/*.yml` và `tenants/partners.yml` vào Postgres (FR-OPS-01, spec 04 §1.3).

1. Đọc và kiểm tra mọi file. File lỗi thì bỏ qua file đó, ghi lỗi và báo team.
2. Upsert bảng `tenants` (cấu hình đã điền mặc định, `config_hash`, `synced_at`).
3. Khách có trong Postgres nhưng không còn file: `status = 'archived'`, không xóa.
4. Khách mới (chưa từng bootstrap): `bootstrap_required = true` và báo team.

Trường `partners` trong file khách chỉ được đối chiếu và cảnh báo nếu lệch quyền trên cổng (spec 04 §1.2).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.db.models import Partner, PartnerGrant, Tenant
from dx_common.events import publish
from dx_common.tenants import load_partners, validate_dir
from dx_common.timeutil import now_utc


@dataclass
class SyncResult:
    upserted: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    archived: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)
    errors: dict[str, list[str]] = field(default_factory=dict)
    partner_mismatch: dict[str, dict[str, list[str]]] = field(default_factory=dict)


def config_hash(config: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def sync_tenants(db: Session, tenants_dir: str | Path, producer: str = "s4-ops") -> SyncResult:
    res = SyncResult()
    for pid, p in load_partners(tenants_dir).items():
        prow = db.get(Partner, pid)
        if prow is None:
            db.add(Partner(partner_id=pid, name=p.name, contact_email=p.contact_email))
        else:
            prow.name, prow.contact_email = p.name, p.contact_email
    db.flush()

    ok, errs = validate_dir(tenants_dir)
    for e in errs:
        res.errors[e.path] = e.errors
        publish("tenant.config_invalid", None, {"path": Path(e.path).name, "errors": e.errors[:20]}, producer, bind=db)

    now = now_utc()
    existing = {t.tenant_id: t for t in db.scalars(select(Tenant))}
    failed_ids = {Path(p).stem for p in res.errors}
    for tid, cfg in ok.items():
        config = cfg.model_dump(mode="json")
        h = config_hash(config)
        row = existing.get(tid)
        if row is None:
            db.add(
                Tenant(
                    tenant_id=tid,
                    name=cfg.name,
                    status=cfg.status,
                    pack=cfg.pack,
                    config=config,
                    config_hash=h,
                    bootstrap_required=True,
                    synced_at=now,
                )
            )
            res.new.append(tid)
            res.upserted.append(tid)
            db.flush()
            publish("tenant.bootstrap_required", tid, {}, producer, bind=db)
            audit(db, action="tenant.registered", tenant_id=tid, actor_service="sync_tenants")
        else:
            if row.config_hash == h and row.status == cfg.status:
                row.synced_at = now
                res.unchanged.append(tid)
            else:
                row.name, row.status, row.pack, row.config, row.config_hash, row.synced_at = (
                    cfg.name,
                    cfg.status,
                    cfg.pack,
                    config,
                    h,
                    now,
                )
                res.upserted.append(tid)
                audit(
                    db,
                    action="tenant.config_synced",
                    tenant_id=tid,
                    actor_service="sync_tenants",
                    detail={"config_hash": h},
                )
        active_grants = set(
            db.scalars(
                select(PartnerGrant.partner_id).where(PartnerGrant.tenant_id == tid, PartnerGrant.revoked_at.is_(None))
            )
        )
        declared = set(cfg.partners)
        if declared != active_grants:
            res.partner_mismatch[tid] = {
                "in_file_only": sorted(declared - active_grants),
                "on_portal_only": sorted(active_grants - declared),
            }

    for tid, row in existing.items():
        if tid not in ok and tid not in failed_ids and row.status != "archived":
            row.status = "archived"
            row.synced_at = now
            res.archived.append(tid)
            audit(db, action="tenant.archived", tenant_id=tid, actor_service="sync_tenants")
    db.flush()
    return res
