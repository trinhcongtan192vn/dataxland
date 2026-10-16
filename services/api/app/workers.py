"""Worker nền của API: `python -m app.workers` (spec 05 §1, service compose `api-worker`).

Mỗi 30 giây: trung tâm thông báo đọc sự kiện mới và gửi tin đến hạn (spec 04 §5); báo team khi có sự kiện
xử lý lỗi quá 5 lần; dọn bộ đếm giới hạn tần suất cũ.
"""

from __future__ import annotations

import signal
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy.orm import Session

from app.notify import dispatcher
from dx_common.db import session_scope
from dx_common.logging import configure_logging, get_logger

log = get_logger("api.worker")
INTERVAL_SECONDS = 30
_stop = False


@contextmanager
def db_scope() -> Iterator[Session]:
    with session_scope() as db:
        yield db


def tick() -> dict[str, Any]:
    stats: dict[str, Any] = {}
    try:
        stats["notify"] = dispatcher.run_once(db_scope)
    except Exception:
        log.exception("vòng thông báo lỗi")
    try:
        from app.jobs import extra_jobs

        stats["jobs"] = extra_jobs(db_scope)
    except Exception:
        log.exception("job phụ lỗi")
    return stats


def main() -> None:
    configure_logging()

    def _handle(*_: object) -> None:
        global _stop
        _stop = True

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)
    log.info("worker bắt đầu")
    while not _stop:
        stats = tick()
        log.info("worker tick", extra={"dx": stats})
        for _ in range(INTERVAL_SECONDS):
            if _stop:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()
