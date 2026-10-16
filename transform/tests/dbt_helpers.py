"""Hàm dùng chung cho test dbt chạy thật trên DuckDB với dữ liệu mẫu cố định (spec 02 §8, §9).

Mỗi phiên test dựng một file DuckDB tạm, nạp `transform/samples/`, chạy `dbt build` cho hai khách giả lập.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "ops"))
os.environ.setdefault("DX_ENV", "local")

TODAY = "2026-10-16"
SALT = "test-salt-0123456789"


@dataclass
class Built:
    path: Path
    tmp: Path

    def con(self) -> Any:
        import duckdb

        return duckdb.connect(str(self.path), read_only=True)


def dbt_run(
    duckdb_path: Path,
    tenant: str,
    *,
    extra_vars: dict[str, Any] | None = None,
    select: list[str] | None = None,
    target_name: str = "t",
    swap: bool = True,
    exclude: list[str] | None = None,
) -> Any:
    from dx_common.tenants import validate_dir
    from dx_pipelines.dbt import DbtProject
    from dx_pipelines.overrides import load_overrides
    from dx_pipelines.warehouse import DuckDBWarehouse

    tenants, _ = validate_dir(REPO / "tenants")
    cfg = tenants[tenant]
    wh = DuckDBWarehouse(duckdb_path)
    load_overrides(cfg, REPO, wh, f"{cfg.dataset_prefix}_raw")
    v = cfg.dbt_vars()
    v["today"] = TODAY
    v.update(extra_vars or {})
    env = {"DX_PII_SALT": SALT, "DUCKDB_PATH": str(duckdb_path)}
    target = duckdb_path.parent / f"target_{tenant}_{target_name}"
    dbt = DbtProject()
    res = dbt.build(v, target, env, select=select, exclude=exclude)
    if swap and not res.runtime_error:
        dbt.run_operation("dx_swap_marts", {}, v, target, env)
    return res


def seed(duckdb_path: Path, samples: Path | None = None) -> None:
    import seed_local

    from dx_common.tenants import validate_dir

    tenants, _ = validate_dir(REPO / "tenants")
    seed_local.seed_duckdb(duckdb_path, samples or REPO / "transform" / "samples", tenants)
