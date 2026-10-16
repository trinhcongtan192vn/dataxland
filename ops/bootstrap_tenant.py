"""`ops/bootstrap_tenant.py <tenant_id> [--env dev|prod]` – tạo môi trường cho khách (FR-OPS-02, spec 04 §2).

Chạy lại không tạo trùng. Ở `local` chỉ tạo schema DuckDB và secret trong `.secrets/`.
Ở `dev`, `prod` dùng `gcloud` và `bq` (cần đăng nhập với quyền quản trị project):

| Bước | Việc |
|---|---|
| 1 | Đọc cấu hình từ Postgres (khách phải đã được đồng bộ) |
| 2 | Tạo dataset `t_<id>_raw`, `_stg`, `_core`, `_marts` ở `warehouse.location`, nhãn `tenant_id=<id>` |
| 3 | Tạo tài khoản dịch vụ `dxt-<slug>` |
| 4 | `dataEditor` trên 4 dataset; `dataViewer` trên `dx_ref`; `jobUser` ở project; `dataViewer` trên marts cho `dx-cube` |
| 5 | Tạo secret `dx-<id>-pii-salt` (32 byte ngẫu nhiên, không đổi khi đã có) |
| 6 | Kiểm tra mọi `secret_ref` tồn tại |
| 7 | Tạo view Windsor nếu cần (spec 01 §8.2) |
| 8 | Đặt `bootstrap_required = false`, phát `tenant.created` |
| 9 | In checklist thủ công |
"""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "services" / "api"))
sys.path.insert(0, str(REPO / "pipelines"))

from sqlalchemy.orm import Session  # noqa: E402

from app.audit import audit  # noqa: E402
from app.db.models import Tenant  # noqa: E402
from dx_common.config import Settings, get_settings  # noqa: E402
from dx_common.db import session_scope  # noqa: E402
from dx_common.events import publish  # noqa: E402
from dx_common.secrets import SecretStore, get_secret_store  # noqa: E402
from dx_common.tenants import TenantConfig  # noqa: E402
from dx_common.tenants.naming import datasets, pii_salt_secret, service_account_id  # noqa: E402

WINDSOR_TABLES = {
    "meta_ads": ["ad_insights_daily"],
    "tiktok_ads": ["ad_insights_daily"],
    "google_ads": ["ad_insights_daily"],
    "amazon_ads": ["ad_insights_daily"],
    "amazon_seller": ["orders", "order_items", "financial_events", "daily_totals"],
}


@dataclass
class BootstrapReport:
    tenant_id: str
    created_datasets: list[str] = field(default_factory=list)
    existing_datasets: list[str] = field(default_factory=list)
    service_account: str | None = None
    salt_created: bool = False
    missing_secrets: list[str] = field(default_factory=list)
    windsor_views: list[str] = field(default_factory=list)
    published_created: bool = False
    checklist: list[str] = field(default_factory=list)


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:  # pragma: no cover - cần GCP
    exe = shutil.which(cmd[0])
    if exe is None:
        raise RuntimeError(f"cần cài {cmd[0]}")
    return subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, check=check)


def _gcp_setup(cfg: TenantConfig, s: Settings, rep: BootstrapReport) -> None:  # pragma: no cover - cần GCP
    project, loc = s.gcp_project_id or cfg.warehouse.project, cfg.warehouse.location
    for ds in datasets(cfg.tenant_id):
        r = _run(
            ["bq", "--location", loc, "mk", "--dataset", "--label", f"tenant_id:{cfg.tenant_id}", f"{project}:{ds}"],
            check=False,
        )
        (rep.created_datasets if r.returncode == 0 else rep.existing_datasets).append(ds)
    sa = service_account_id(cfg.tenant_id)
    email = f"{sa}@{project}.iam.gserviceaccount.com"
    r = _run(["gcloud", "iam", "service-accounts", "describe", email, "--project", project], check=False)
    if r.returncode != 0:
        _run(
            [
                "gcloud",
                "iam",
                "service-accounts",
                "create",
                sa,
                "--project",
                project,
                "--display-name",
                f"DataxLand {cfg.tenant_id}",
            ]
        )
    rep.service_account = email
    for ds in datasets(cfg.tenant_id):
        _grant_dataset(project, ds, email, "WRITER")
    _grant_dataset(project, "dx_ref", email, "READER")
    _grant_dataset(project, f"t_{cfg.tenant_id}_marts", f"dx-cube@{project}.iam.gserviceaccount.com", "READER")
    _run(
        [
            "gcloud",
            "projects",
            "add-iam-policy-binding",
            project,
            "--member",
            f"serviceAccount:{email}",
            "--role",
            "roles/bigquery.jobUser",
            "--condition",
            "None",
            "--quiet",
        ]
    )


def _grant_dataset(project: str, ds: str, member: str, role: str) -> None:  # pragma: no cover - cần GCP
    r = _run(["bq", "show", "--format=prettyjson", f"{project}:{ds}"])
    info = json.loads(r.stdout)
    access = info.get("access", [])
    if not any(a.get("userByEmail") == member and a.get("role") == role for a in access):
        access.append({"role": role, "userByEmail": member})
        tmp = Path(".local") / f"acl_{ds}.json"
        tmp.parent.mkdir(exist_ok=True)
        tmp.write_text(json.dumps({"access": access}))
        _run(["bq", "update", "--source", str(tmp), f"{project}:{ds}"])
        tmp.unlink()


def windsor_view_sql(cfg: TenantConfig, source: str, obj: str, project: str | None) -> str:
    """View trong `t_<id>_raw` khi Windsor ghi vào `t_<id>_windsor` (spec 01 §8.2)."""
    q = (lambda x: f"`{project}.{x}`") if project else (lambda x: f'"{x.split(".")[0]}"."{x.split(".")[1]}"')
    raw = f"t_{cfg.tenant_id}_raw.{source}__{obj}"
    src = f"t_{cfg.tenant_id}_windsor.{source}__{obj}"
    return (
        f"CREATE OR REPLACE VIEW {q(raw)} AS SELECT *, datetime_synced AS _dx_loaded_at, "
        f"CAST(account_id AS STRING) AS _dx_source_account FROM {q(src)}"
    )


def bootstrap(
    db: Session,
    tenant_id: str,
    *,
    settings: Settings | None = None,
    store: SecretStore | None = None,
    warehouse: Any = None,
    gcp: bool | None = None,
) -> BootstrapReport:
    s = settings or get_settings()
    store = store or get_secret_store(s)
    row = db.get(Tenant, tenant_id)
    if row is None:
        raise SystemExit(f"Khách {tenant_id} chưa được đồng bộ. Chạy ops/sync_tenants.py trước.")
    cfg = TenantConfig.model_validate(row.config)
    rep = BootstrapReport(tenant_id)
    use_gcp = (not s.is_local) if gcp is None else gcp
    if use_gcp:  # pragma: no cover - cần GCP
        _gcp_setup(cfg, s, rep)
    else:
        from dx_pipelines.warehouse import DuckDBWarehouse

        wh = warehouse or DuckDBWarehouse(s.duckdb_path)
        for ds in datasets(tenant_id):
            (rep.created_datasets if wh.ensure_dataset(ds, {"tenant_id": tenant_id}) else rep.existing_datasets).append(
                ds
            )
        wh.ensure_dataset("dx_ref", {})
    name = pii_salt_secret(tenant_id)
    if not store.exists(name):
        store.put(name, secrets.token_hex(32))
        rep.salt_created = True
    for src in cfg.enabled_sources():
        if src.secret_ref and not store.exists(src.secret_ref):
            rep.missing_secrets.append(src.secret_ref)
    if use_gcp:  # pragma: no cover - cần GCP
        windsor_ds = f"t_{tenant_id}_windsor"
        r = _run(["bq", "ls", "--format=json", f"{s.gcp_project_id}:{windsor_ds}"], check=False)
        if r.returncode == 0:
            for src in cfg.enabled_sources():
                for obj in WINDSOR_TABLES.get(src.type, []) if src.connector == "windsor" else []:
                    _run(
                        [
                            "bq",
                            "query",
                            "--use_legacy_sql=false",
                            windsor_view_sql(cfg, src.type, obj, s.gcp_project_id),
                        ]
                    )
                    rep.windsor_views.append(f"{src.type}__{obj}")
    if row.bootstrap_required:
        row.bootstrap_required = False
        publish("tenant.created", tenant_id, {}, "s4-ops", bind=db)
        audit(
            db,
            action="tenant.bootstrapped",
            tenant_id=tenant_id,
            actor_service="bootstrap_tenant",
            detail={"datasets": rep.created_datasets},
        )
        rep.published_created = True
    rep.checklist = checklist(cfg, rep)
    return rep


def checklist(cfg: TenantConfig, rep: BootstrapReport) -> list[str]:
    items = []
    for src in cfg.enabled_sources():
        if src.connector == "windsor":
            items.append(f"Kết nối Windsor cho {src.type} (tài khoản {src.account_id}) → xem /ops/integrations/windsor")
        elif src.type in ("shopee", "tiktok_shop", "lazada"):
            items.append(
                f"Cấp quyền OAuth cho {src.type} tại /ops/tenants/{cfg.tenant_id} → /ops/integrations/{src.type}"
            )
    for m in rep.missing_secrets:
        items.append(f"Tạo secret còn thiếu: {m}")
    items.append("Mời owner (POST /v1/members/invitations, role owner) và hướng dẫn liên kết Telegram")
    return items


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tenant_id")
    ap.add_argument("--env", choices=["local", "dev", "prod"], default=None)
    args = ap.parse_args()
    s = get_settings()
    with session_scope() as db:
        rep = bootstrap(db, args.tenant_id, settings=s, gcp=(args.env in ("dev", "prod")) if args.env else None)
    print(json.dumps(rep.__dict__, ensure_ascii=False, indent=2))
    print("\nChecklist thủ công:")
    for i, item in enumerate(rep.checklist, 1):
        print(f"  {i}. {item}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
