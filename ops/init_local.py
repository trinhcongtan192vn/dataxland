"""Chuẩn bị máy dev (`make setup`): thư mục `.local/`, `.secrets/` và secret local của khách giả lập.

Không tạo bí mật thật. Muối băm thông tin cá nhân của khách giả lập (`dx-<tenant_id>-pii-salt`) được sinh
ngẫu nhiên một lần và không bao giờ đổi khi đã có (spec 04 §2 bước 5).
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

from dx_common.config import get_settings  # noqa: E402
from dx_common.secrets import LocalFileSecretStore  # noqa: E402


def main() -> int:
    s = get_settings()
    for d in (s.metadata_bucket, s.hc_bucket, Path(s.duckdb_path).parent):
        Path(d).mkdir(parents=True, exist_ok=True)
    store = LocalFileSecretStore(s.secrets_dir)
    for tid in ("demo_seller", "demo_agency"):
        name = f"dx-{tid}-pii-salt"
        if not store.exists(name):
            store.put(name, secrets.token_hex(32))
            print(f"tạo {name}")
    print("Máy dev đã sẵn sàng. Bước tiếp: make up && make seed-local")
    return 0


if __name__ == "__main__":
    sys.exit(main())
