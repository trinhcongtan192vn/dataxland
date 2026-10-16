"""Giới hạn tần suất theo người dùng (spec 05 §8): 120 request/phút mọi endpoint, 30/phút cho
`POST /v1/metrics/query`. Bộ đếm theo ô 10 giây trong bảng `rate_counters` (GĐ1).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import RateCounter
from app.errors import ApiError
from dx_common.timeutil import now_utc

BUCKET_SECONDS = 10


def _bucket(ts: datetime) -> datetime:
    return ts.replace(second=ts.second - ts.second % BUCKET_SECONDS, microsecond=0)


def hit(db: Session, key: str, limit: int, window_seconds: int) -> int | None:
    """Tăng bộ đếm; vượt giới hạn thì trả số giây cần chờ, nếu không trả None."""
    now = now_utc()
    b = _bucket(now)
    stmt = insert(RateCounter).values(key=key, bucket=b, count=1)
    db.execute(stmt.on_conflict_do_update(index_elements=["key", "bucket"], set_={"count": RateCounter.count + 1}))
    since = now - timedelta(seconds=window_seconds)
    total = db.scalar(
        select(func.coalesce(func.sum(RateCounter.count), 0)).where(RateCounter.key == key, RateCounter.bucket > since)
    )
    if int(total or 0) > limit:
        return BUCKET_SECONDS
    return None


def check_user_rate(db: Session, user_id: str, path: str, method: str) -> None:
    wait = hit(db, f"user:{user_id}", 120, 60)
    if wait is None and method == "POST" and path.rstrip("/") == "/v1/metrics/query":
        wait = hit(db, f"user:{user_id}:metrics", 30, 60)
    if wait is not None:
        raise ApiError(
            429, "RATE_LIMITED", "Quá nhiều yêu cầu, thử lại sau ít giây", headers={"Retry-After": str(wait)}
        )


def check_key_rate(db: Session, key: str, limit: int, window_seconds: int) -> None:
    wait = hit(db, key, limit, window_seconds)
    if wait is not None:
        raise ApiError(429, "RATE_LIMITED", "Quá nhiều yêu cầu, thử lại sau", headers={"Retry-After": str(wait)})


def cleanup(db: Session, older_than: timedelta = timedelta(days=2)) -> None:
    from sqlalchemy import delete

    db.execute(delete(RateCounter).where(RateCounter.bucket < now_utc() - older_than))
