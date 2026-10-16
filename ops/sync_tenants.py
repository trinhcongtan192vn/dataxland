"""`ops/sync_tenants.py` – đồng bộ sổ đăng ký khách vào Postgres (FR-OPS-01, spec 04 §1.3).

Chạy khi triển khai (spec 00 §8.2) và theo lịch Dagster `sync_tenants` mỗi 5 phút.
`--git-fetch`: lấy thư mục `tenants/` mới nhất từ nhánh `main` bằng deploy key chỉ đọc trước khi đồng bộ.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "services" / "api"))

from app.registry_sync import sync_tenants  # noqa: E402
from dx_common.db import session_scope  # noqa: E402


def git_fetch_tenants(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "fetch", "--quiet", "origin", "main"], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "origin/main", "--", "tenants"], check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(REPO / "tenants"))
    ap.add_argument("--git-fetch", action="store_true")
    args = ap.parse_args()
    if args.git_fetch:
        git_fetch_tenants(REPO)
    with session_scope() as db:
        res = sync_tenants(db, args.dir)
    print(json.dumps(res.__dict__, ensure_ascii=False, indent=2))
    return 1 if res.errors else 0


if __name__ == "__main__":
    sys.exit(main())
