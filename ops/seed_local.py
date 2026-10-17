"""`make seed-local` – nạp dữ liệu mẫu cho `demo_seller`, `demo_agency` (spec 00 §5, spec 02 §8).

1. Lấy dữ liệu mẫu: mặc định sinh lại bằng `ops/gen_samples.py` với ngày cuối là hôm qua (giờ Việt Nam) vào
   `.local/samples/`, để dashboard và báo cáo có số của tuần hiện tại. Bộ sinh dùng seed cố định nên đây là
   cùng bộ dữ liệu trong `transform/samples/`, chỉ dời ngày. `--fixed` nạp nguyên `transform/samples/`.
2. Nạp vào DuckDB (`DUCKDB_PATH`): mỗi khách một schema `t_<tenant_id>_raw`, mỗi bảng `<source>__<object>`,
   chỉ lấy bản ghi có `_dx_source_account` khớp tài khoản trong `tenants/<id>.yml`. Tỷ giá vào `dx_ref.fx_rates`.
3. Nạp giá vốn và ngân sách mẫu vào Postgres (`product_costs`, `ad_budgets`) nếu đã chạy `alembic upgrade head`.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "ops"))

from dx_common.config import get_settings  # noqa: E402
from dx_common.tenants import TenantConfig, validate_dir  # noqa: E402
from dx_common.timeutil import today_vn  # noqa: E402

DEMO_TENANTS = ("demo_seller", "demo_agency")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _write_tmp(rows: Iterable[dict[str, Any]], tmpdir: Path, name: str) -> Path:
    p = tmpdir / f"{name}.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return p


def load_table(con: Any, schema: str, table: str, rows: list[dict[str, Any]], tmpdir: Path) -> int:
    con.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    if not rows:
        return 0
    p = _write_tmp(rows, tmpdir, f"{schema}__{table}")
    path_sql = str(p).replace("\\", "/").replace("'", "''")
    con.execute(
        f'CREATE OR REPLACE TABLE "{schema}"."{table}" AS '
        f"SELECT * FROM read_json_auto('{path_sql}', format='newline_delimited', sample_size=-1)"
    )
    # Cột toàn null được DuckDB suy ra kiểu JSON; đổi về VARCHAR để staging ép kiểu ổn định.
    json_cols = [
        r[0]
        for r in con.execute(
            "select column_name from information_schema.columns where table_schema = ? and table_name = ? "
            "and data_type = 'JSON'",
            [schema, table],
        ).fetchall()
    ]
    for col in json_cols:
        con.execute(f'ALTER TABLE "{schema}"."{table}" ALTER COLUMN "{col}" TYPE VARCHAR')
    return len(rows)


def load_tenant_raw(
    con: Any, cfg: TenantConfig, samples: Path, tmpdir: Path, prefix: str | None = None
) -> dict[str, int]:
    schema = f"{prefix or cfg.dataset_prefix}_raw"
    out: dict[str, int] = {}
    for src in cfg.enabled_sources():
        folder = samples / src.type
        if not folder.is_dir():
            continue
        for f in sorted(folder.glob("*.jsonl")):
            rows = read_jsonl(f)
            if src.type == "portal":
                rows = [r for r in rows if r.get("tenant_id") == cfg.tenant_id]
            else:
                rows = [r for r in rows if r.get("_dx_source_account") == src.account_id]
            table = f"{src.type}__{f.stem}"
            out[table] = load_table(con, schema, table, rows, tmpdir)
    return out


def load_fx(con: Any, samples: Path, tmpdir: Path) -> int:
    rows = read_jsonl(samples / "fx_vcb" / "fx_rates.jsonl")
    return load_table(con, "dx_ref", "fx_rates", rows, tmpdir)


def seed_duckdb(duckdb_path: str | Path, samples: Path, tenants: dict[str, TenantConfig]) -> dict[str, dict[str, int]]:
    import duckdb

    Path(duckdb_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(duckdb_path))
    result: dict[str, dict[str, int]] = {}
    try:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            result["dx_ref"] = {"fx_rates": load_fx(con, samples, tmp)}
            for tid in DEMO_TENANTS:
                if tid in tenants:
                    result[tid] = load_tenant_raw(con, tenants[tid], samples, tmp)
    finally:
        con.close()
    return result


def seed_postgres(samples: Path) -> str:
    """Nạp giá vốn và ngân sách mẫu vào Postgres. Bỏ qua nếu chưa có bảng."""
    from sqlalchemy import inspect, text

    from dx_common.db import get_engine

    try:
        eng = get_engine()
        insp = inspect(eng)
        if not insp.has_table("product_costs"):
            return "bỏ qua Postgres: chưa có bảng (chạy `alembic upgrade head` trước)"
    except Exception as exc:  # Postgres chưa bật
        return f"bỏ qua Postgres: {type(exc).__name__}"
    costs = read_jsonl(samples / "portal" / "product_costs.jsonl")
    budgets = read_jsonl(samples / "portal" / "ad_budgets.jsonl")
    now = datetime.now(UTC)
    with eng.begin() as conn:
        for tid in DEMO_TENANTS:
            conn.execute(text("delete from product_costs where tenant_id = :t"), {"t": tid})
            conn.execute(text("delete from ad_budgets where tenant_id = :t"), {"t": tid})
        for r in costs:
            conn.execute(
                text(
                    "insert into product_costs (id, tenant_id, seller_sku, unit_cost_vnd, valid_from, note, created_by,"
                    " deleted_at, created_at, updated_at) values (:id, :tenant_id, :seller_sku, :unit_cost_vnd,"
                    " :valid_from, :note, 'seed', null, :now, :now)"
                ),
                {
                    **{k: r[k] for k in ("tenant_id", "seller_sku", "unit_cost_vnd", "valid_from", "note")},
                    "id": "seed" + r["id"].upper().rjust(22, "0"),
                    "now": now,
                },
            )
        for r in budgets:
            conn.execute(
                text(
                    "insert into ad_budgets (id, tenant_id, platform, month, budget_vnd, created_by, deleted_at,"
                    " created_at, updated_at) values (:id, :tenant_id, :platform, :month, :budget_vnd, 'seed', null,"
                    " :now, :now)"
                ),
                {
                    **{k: r[k] for k in ("tenant_id", "platform", "month", "budget_vnd")},
                    "id": "seed" + r["id"].upper().rjust(22, "0"),
                    "now": now,
                },
            )
    return f"Postgres: {len(costs)} giá vốn, {len(budgets)} ngân sách"


def prepare_samples(fixed: bool) -> Path:
    if fixed:
        return REPO / "transform" / "samples"
    import gen_samples

    out = REPO / ".local" / "samples"
    anchor = today_vn() - timedelta(days=1)
    tables = gen_samples.generate(anchor, datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=5))
    gen_samples.write_tables(tables, out)
    gen_samples.build_hc_files(tables, out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixed", action="store_true", help="nạp nguyên transform/samples (ngày cố định)")
    ap.add_argument("--skip-postgres", action="store_true")
    args = ap.parse_args()
    s = get_settings()
    tenants, errs = validate_dir(REPO / "tenants")
    if errs:
        for e in errs:
            print(f"LỖI cấu hình: {e}")
        return 1
    samples = prepare_samples(args.fixed)
    res = seed_duckdb(s.duckdb_path, samples, tenants)
    for scope, tables in res.items():
        print(f"{scope}: " + ", ".join(f"{t}={n}" for t, n in sorted(tables.items())))
    if not args.skip_postgres:
        print(seed_postgres(samples))
        sys.path.insert(0, str(REPO / "ops"))
        from seed_users import seed_demo_users

        print(seed_demo_users())
    return 0


if __name__ == "__main__":
    sys.exit(main())
