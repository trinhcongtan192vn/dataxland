"""ID trong Postgres là ULID dạng chuỗi 26 ký tự (spec 00 §3.1)."""

from __future__ import annotations

import secrets
from datetime import datetime

from ulid import ULID


def new_ulid() -> str:
    return str(ULID())


def ulid_at(ts: datetime) -> str:
    """ULID nhỏ nhất của một thời điểm, dùng làm cận dưới khi quét sự kiện."""
    return str(ULID.from_timestamp(ts.timestamp()))[:10] + "0" * 16


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)
