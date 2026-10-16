"""`make dbt-build TENANT=demo_seller` – chạy dbt cho một khách trên máy dev (spec 00 §6, spec 02 §9).

Làm như các bước `load_overrides`, `dbt_build`, `evaluate_tests`, `swap_marts` của `tenant_pipeline` nhưng không cần
Dagster, API hay Cube. `--fixed-samples`: nạp nguyên `transform/samples/` vào `DUCKDB_PATH` và cố định hôm nay là
2026-10-16 (dùng trong CI và test).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "ops"))

from dx_common.config import get_settings  # noqa: E402
from dx_common.secrets import SecretNotFound, get_secret_store  # noqa: E402
from dx_common.tenants import validate_dir  # noqa: E402
from dx_common.tenants.naming import pii_salt_secret  # noqa: E402
from dx_pipelines.dbt import DbtProject, blocking_failures, warning_failures  # noqa: E402
from dx_pipelines.overrides import load_overrides  # noqa: E402
from dx_pipelines.warehouse import DuckDBWarehouse, get_warehouse  # noqa: E402

FIXED_TODAY = "2026-10-16"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tenant")
    ap.add_argument("--fixed-samples", action="store_true")
    ap.add_argument("--today", default=None)
    ap.add_argument("--select", nargs="*", default=None)
    ap.add_argument("--full-refresh", action="store_true")
    ap.add_argument("--no-swap", action="store_true")
    ap.add_argument("--freshness", action="store_true", help="chạy thêm dbt source freshness")
    args = ap.parse_args()

    s = get_settings()
    tenants, errs = validate_dir(REPO / "tenants")
    if args.tenant not in tenants:
        print(f"Không có khách {args.tenant}: {[str(e) for e in errs]}")
        return 2
    cfg = tenants[args.tenant]
    today = args.today
    if args.fixed_samples:
        import seed_local

        seed_local.seed_duckdb(s.duckdb_path, REPO / "transform" / "samples", tenants)
        today = today or FIXED_TODAY
    wh = DuckDBWarehouse(s.duckdb_path) if s.is_local else get_warehouse(cfg.tenant_id, job="dbt")
    load_overrides(cfg, REPO, wh, f"{cfg.dataset_prefix}_raw")
    try:
        salt = get_secret_store().get(pii_salt_secret(cfg.tenant_id))
    except SecretNotFound:
        salt = os.environ.get("DX_PII_SALT", "local-test-salt")
    env = {"DX_PII_SALT": salt, "DX_TENANT_ID": cfg.tenant_id}
    vars_ = cfg.dbt_vars()
    if today:
        vars_["today"] = today
    target = REPO / "transform" / "target" / "runs" / cfg.tenant_id / "manual"
    dbt = DbtProject()
    fresh = dbt.freshness(vars_, target, env) if args.freshness else None
    res = dbt.build(vars_, target, env, select=args.select, full_refresh=args.full_refresh)
    print(res.stdout_tail[-5000:])
    failures = blocking_failures(res, fresh)
    warns = warning_failures(res)
    print(
        json.dumps(
            {"returncode": res.returncode, "blocking": [f["unique_id"] for f in failures], "warnings": warns},
            ensure_ascii=False,
            indent=2,
        )
    )
    if res.runtime_error or failures:
        return 1
    if not args.no_swap:
        sw = dbt.run_operation("dx_swap_marts", {}, vars_, target, env)
        if not sw.ok:
            print(sw.stdout_tail[-2000:])
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
