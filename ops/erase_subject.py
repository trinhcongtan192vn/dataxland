"""Xóa dữ liệu một người mua theo yêu cầu (FR-OPS-09, spec 04 §8).

    uv run python ops/erase_subject.py --tenant <id> (--phone <số> | --email <email> | --buyer-ref <source>:<mã>) [--dry-run]

1. Tính `phone_hash`/`email_hash` bằng muối của khách (cùng cách với macro `pii_hash`).
2. Tra `transform/pii_columns.yml` để tìm bản ghi khớp trong `raw`.
3. Bảng đơn: đặt null mọi cột thông tin cá nhân của bản ghi khớp, giữ đơn để không sai doanh thu.
4. Chạy dbt `--full-refresh` cho các model có thông tin người mua (`stg_<sàn>__orders` và mọi model phía sau), rồi
   hoán đổi marts, để `stg`, `core`, `marts` không còn bản ghi gốc hay băm. Xóa dòng `identity_map` của người đó.
5. Ghi `erasure_log` (chỉ giá trị băm). `--dry-run` chỉ đếm.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipelines"))

from dx_common.config import get_settings  # noqa: E402
from dx_common.secrets import SecretNotFound, get_secret_store  # noqa: E402
from dx_common.tenants import TenantConfig, validate_dir  # noqa: E402
from dx_common.tenants.naming import pii_salt_secret  # noqa: E402
from dx_common.timeutil import now_utc  # noqa: E402


@dataclass
class Identifier:
    kind: str  # phone | email | buyer_ref
    value: str  # đã chuẩn hóa
    source: str | None = None  # với buyer_ref

    def matches(self, table_cfg: dict[str, Any], row: dict[str, Any]) -> bool:
        if self.kind == "buyer_ref":
            if table_cfg.get("source") != self.source:
                return False
            return any(str(row.get(c) or "") == self.value for c in table_cfg.get("buyer_ref", []))
        cols = table_cfg.get(self.kind, [])
        norm = norm_phone if self.kind == "phone" else norm_email
        return any(row.get(c) and norm(str(row[c])) == self.value for c in cols)


def norm_phone(v: str) -> str:
    digits = re.sub(r"[^0-9]", "", v)
    return "0" + digits[2:] if digits.startswith("84") else digits


def norm_email(v: str) -> str:
    return v.strip().lower()


def identifier_hash(salt: str, ident: Identifier) -> str:
    """SHA-256 hex của `salt || giá trị chuẩn hóa`, như macro `pii_hash`; mã người mua kèm tên nguồn."""
    value = f"{ident.source}:{ident.value}" if ident.kind == "buyer_ref" else ident.value
    return hashlib.sha256(f"{salt}{value}".encode()).hexdigest()


def pii_config() -> dict[str, dict[str, Any]]:
    return dict(yaml.safe_load((REPO / "transform" / "pii_columns.yml").read_text(encoding="utf-8")))


@dataclass
class EraseResult:
    identifier_hash: str
    rows: dict[str, int] = field(default_factory=dict)
    dry_run: bool = False
    dbt_ok: bool | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "identifier_hash": self.identifier_hash,
            "rows_affected": self.rows,
            "dry_run": self.dry_run,
            "dbt_ok": self.dbt_ok,
        }


def _q(wh: Any, name: str) -> str:
    return f'"{name}"' if wh.kind == "duckdb" else f"`{name}`"


def _lit(v: Any) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def erase(
    tenant: TenantConfig,
    ident: Identifier,
    salt: str,
    warehouse: Any,
    *,
    dry_run: bool = False,
    run_dbt: Callable[[TenantConfig, list[str]], bool] | None = None,
) -> EraseResult:
    raw = f"{tenant.dataset_prefix}_raw"
    res = EraseResult(identifier_hash=identifier_hash(salt, ident), dry_run=dry_run)
    tables = set(warehouse.list_tables(raw))
    enabled = {s.type for s in tenant.enabled_sources()}
    touched_sources: list[str] = []
    matched: dict[str, set[str]] = {}
    for table, cfg in pii_config().items():
        if table not in tables or cfg["source"] not in enabled:
            continue
        cols = [c for k in ("phone", "email", "name", "address", "buyer_ref") for c in cfg.get(k, [])]
        existing = (
            {
                r[0]
                for r in warehouse.query(
                    "select column_name from information_schema.columns where table_schema = ? and table_name = ?",
                    [raw, table],
                )
            }
            if warehouse.kind == "duckdb"
            else set(cols)
        )
        cols = [c for c in cols if c in existing]
        if not cols:
            continue
        key = cfg["key"]
        fq = f"{_q(warehouse, raw)}.{_q(warehouse, table)}"
        rows = warehouse.query(f"select {_q(warehouse, key)}, {', '.join(_q(warehouse, c) for c in cols)} from {fq}")
        keys = sorted({str(r[0]) for r in rows if ident.matches(cfg, dict(zip([key, *cols], r, strict=True)))})
        if not keys:
            continue
        n = sum(1 for r in rows if str(r[0]) in keys)
        res.rows[table] = n
        touched_sources.append(cfg["source"])
        matched.setdefault(cfg["source"], set()).update(keys)
        if dry_run:
            continue
        sets = ", ".join(f"{_q(warehouse, c)} = null" for c in cols)
        in_list = ", ".join(_lit(k) for k in keys)
        warehouse.execute(
            f"update {fq} set {sets} where cast({_q(warehouse, key)} as varchar) in ({in_list})"
            if warehouse.kind == "duckdb"
            else f"update {fq} set {sets} where cast({_q(warehouse, key)} as string) in ({in_list})"
        )
    if dry_run or not touched_sources:
        return res
    # identity_map (spec 10 §8): bỏ các dòng ghép người mua theo mã nguồn của đơn bị xóa thông tin.
    core = f"{tenant.dataset_prefix}_core"
    if "identity_map" in set(warehouse.list_tables(core)):
        for source, ids in sorted(matched.items()):
            warehouse.execute(
                f"delete from {_q(warehouse, core)}.{_q(warehouse, 'identity_map')} "
                f"where entity = 'customer' and source = {_lit(source)} "
                f"and source_id in ({', '.join(_lit(k) for k in sorted(ids))})"
            )
    if run_dbt is not None:
        res.dbt_ok = run_dbt(tenant, sorted(set(touched_sources)))
    return res


def dbt_full_refresh(tenant: TenantConfig, sources: list[str], salt: str) -> bool:
    """dbt `--full-refresh` cho `stg_<sàn>__orders` và mọi model phía sau, rồi hoán đổi marts."""
    from dx_pipelines.dbt import DbtProject, blocking_failures

    vars_ = tenant.dbt_vars()
    if os.environ.get("DX_TODAY"):
        vars_["today"] = os.environ["DX_TODAY"]
    env = {"DX_PII_SALT": salt, "DX_TENANT_ID": tenant.tenant_id}
    target = REPO / "transform" / "target" / "runs" / tenant.tenant_id / "erase"
    dbt = DbtProject()
    build = dbt.build(
        vars_,
        target,
        env,
        select=[f"stg_{s}__orders+" for s in sources],
        exclude=["resource_type:unit_test"],
        full_refresh=True,
    )
    if build.runtime_error or blocking_failures(build, None):
        print(build.stdout_tail[-3000:])
        return False
    return dbt.run_operation("dx_swap_marts", {}, vars_, target, env).ok


def write_log(tenant_id: str, res: EraseResult, operator: str, requested_at: Any) -> None:
    from sqlalchemy import text

    from dx_common.db import get_engine
    from dx_common.ids import new_ulid

    with get_engine().begin() as conn:
        conn.execute(
            text(
                "insert into erasure_log (id, tenant_id, requested_at, completed_at, identifier_hash, rows_affected,"
                " operator, dry_run, created_at, updated_at) values (:id, :t, :req, :done, :h, cast(:rows as jsonb), :op,"
                " :dry, now(), now())"
            ),
            {
                "id": new_ulid(),
                "t": tenant_id,
                "req": requested_at,
                "done": None if res.dry_run else now_utc(),
                "h": res.identifier_hash,
                "rows": json.dumps(res.rows),
                "op": operator,
                "dry": res.dry_run,
            },
        )
        conn.execute(
            text(
                "insert into audit_log (id, action, tenant_id, actor_service, target, detail, created_at, updated_at)"
                " values (:id, 'erasure.executed', :t, 'ops', :h, cast(:d as jsonb), now(), now())"
            ),
            {
                "id": new_ulid(),
                "t": tenant_id,
                "h": res.identifier_hash,
                "d": json.dumps({"rows_affected": res.rows, "dry_run": res.dry_run}),
            },
        )


def parse_identifier(args: argparse.Namespace) -> Identifier:
    if args.phone:
        return Identifier("phone", norm_phone(args.phone))
    if args.email:
        return Identifier("email", norm_email(args.email))
    source, _, code = args.buyer_ref.partition(":")
    if not source or not code:
        raise SystemExit("--buyer-ref phải có dạng <source>:<mã>")
    return Identifier("buyer_ref", code.strip(), source.strip())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tenant", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--phone")
    g.add_argument("--email")
    g.add_argument("--buyer-ref")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--operator", default=os.environ.get("USER") or os.environ.get("USERNAME") or "ops")
    ap.add_argument("--no-log", action="store_true", help="không ghi erasure_log (chỉ dùng khi thử)")
    args = ap.parse_args()

    tenants, _ = validate_dir(REPO / "tenants")
    if args.tenant not in tenants:
        print(f"Không có khách {args.tenant}")
        return 2
    cfg = tenants[args.tenant]
    try:
        salt = get_secret_store().get(pii_salt_secret(cfg.tenant_id))
    except SecretNotFound:
        print(f"Thiếu secret {pii_salt_secret(cfg.tenant_id)}")
        return 2
    from dx_pipelines.warehouse import DuckDBWarehouse, get_warehouse

    s = get_settings()
    wh = DuckDBWarehouse(s.duckdb_path) if s.is_local else get_warehouse(cfg.tenant_id, job="erase")
    requested = now_utc()
    res = erase(
        cfg,
        parse_identifier(args),
        salt,
        wh,
        dry_run=args.dry_run,
        run_dbt=lambda t, srcs: dbt_full_refresh(t, srcs, salt),
    )
    if not args.no_log:
        write_log(cfg.tenant_id, res, args.operator, requested)
    print(json.dumps(res.to_json(), ensure_ascii=False, indent=2))
    return 0 if res.dry_run or res.dbt_ok is not False else 1


if __name__ == "__main__":
    sys.exit(main())
