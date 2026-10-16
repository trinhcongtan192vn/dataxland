"""Tiện ích cho test: Postgres tạm.

- Có `DATABASE_URL` trỏ tới Postgres (CI dùng service container): tạo database riêng cho phiên test.
- Không có: chạy Postgres nhúng bằng `pgserver` (máy dev không có Docker).
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text

from dx_common.db import normalize_url
from dx_common.ids import new_ulid


@contextmanager
def ephemeral_postgres() -> Iterator[str]:
    base = os.environ.get("DX_TEST_DATABASE_URL")
    if base:
        base = normalize_url(base)
        name = "dx_test_" + new_ulid().lower()
        admin = create_engine(base, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
        url = base.rsplit("/", 1)[0] + "/" + name
        try:
            yield url
        finally:
            with admin.connect() as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            admin.dispose()
        return

    import pgserver

    data_dir = tempfile.mkdtemp(prefix="dxpg_")
    server = pgserver.get_server(data_dir, cleanup_mode="delete")  # type: ignore[attr-defined]
    try:
        yield normalize_url(server.get_uri())
    finally:
        server.cleanup()
