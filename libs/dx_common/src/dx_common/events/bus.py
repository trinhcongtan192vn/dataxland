"""`publish()` và `consume()` (spec 04 §4.2).

Cài đặt outbox: `event_id` là ULID nên tăng theo thời gian. Vì nhiều bên phát có thể commit lệch thứ tự,
`consume` quét lại một cửa sổ 10 phút trước offset và dựa vào `event_processed` để không xử lý trùng
(bên nhận idempotent theo `event_id`, architecture §11.2).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Connection, Engine, and_, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from dx_common.db import get_engine
from dx_common.events.schemas import payload_model
from dx_common.events.tables import event_dead_letters, event_offsets, event_processed, events
from dx_common.ids import new_ulid, ulid_at
from dx_common.logging import get_logger
from dx_common.timeutil import iso_z, now_utc

log = get_logger(__name__)

MAX_ATTEMPTS = 5
RESCAN_WINDOW = timedelta(minutes=10)


@dataclass(frozen=True)
class Event:
    event_id: str
    type: str
    version: int
    tenant_id: str | None
    occurred_at: datetime
    producer: str
    payload: dict[str, Any]

    def envelope(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "type": self.type,
            "version": self.version,
            "tenant_id": self.tenant_id,
            "occurred_at": iso_z(self.occurred_at),
            "producer": self.producer,
            "payload": self.payload,
        }


Bind = Session | Connection | Engine | None


def publish(
    type: str,
    tenant_id: str | None,
    payload: dict[str, Any],
    producer: str,
    bind: Bind = None,
) -> str:
    """Kiểm tra payload theo model của loại sự kiện rồi ghi một dòng. Dùng transaction của bên gọi nếu có."""
    model = payload_model(type)
    clean = model.model_validate(payload).model_dump(mode="json")
    event_id = new_ulid()
    stmt = insert(events).values(
        event_id=event_id,
        type=type,
        version=1,
        tenant_id=tenant_id,
        occurred_at=now_utc(),
        producer=producer,
        payload=clean,
    )
    if bind is None:
        with get_engine().begin() as conn:
            conn.execute(stmt)
    elif isinstance(bind, Engine):
        with bind.begin() as conn:
            conn.execute(stmt)
    else:
        bind.execute(stmt)
    return event_id


Handler = Callable[[Event], None]


def _row_to_event(row: Any) -> Event:
    return Event(
        event_id=row.event_id,
        type=row.type,
        version=row.version,
        tenant_id=row.tenant_id,
        occurred_at=row.occurred_at,
        producer=row.producer,
        payload=dict(row.payload),
    )


def consume(
    consumer: str,
    types: Iterable[str],
    handler: Handler,
    batch: int = 100,
    engine: Engine | None = None,
) -> int:
    """Xử lý một lô. Trả số sự kiện đã xử lý thành công.

    Lỗi handler thì dừng lô, thử lại ở lần sau; quá 5 lần cho một sự kiện thì đánh dấu `dead`
    trong `event_dead_letters` và bỏ qua để không chặn các sự kiện khác (báo team do bên gọi làm).
    """
    eng = engine or get_engine()
    type_list = sorted(set(types))
    done = 0
    with eng.connect() as conn:
        offset_row = conn.execute(
            select(event_offsets.c.last_event_id).where(event_offsets.c.consumer == consumer)
        ).first()
        floor = ulid_at(now_utc() - RESCAN_WINDOW)
        start = min(offset_row[0], floor) if offset_row else "0"
        rows = conn.execute(
            select(events)
            .outerjoin(
                event_processed,
                and_(event_processed.c.event_id == events.c.event_id, event_processed.c.consumer == consumer),
            )
            .outerjoin(
                event_dead_letters,
                and_(
                    event_dead_letters.c.event_id == events.c.event_id,
                    event_dead_letters.c.consumer == consumer,
                ),
            )
            .where(
                events.c.event_id > start,
                events.c.type.in_(type_list),
                event_processed.c.event_id.is_(None),
                (event_dead_letters.c.dead.is_(None)) | (event_dead_letters.c.dead.is_(False)),
            )
            .order_by(events.c.event_id)
            .limit(batch)
        ).all()

    last_ok: str | None = None
    for row in rows:
        ev = _row_to_event(row)
        try:
            handler(ev)
        except Exception as exc:
            _record_failure(eng, consumer, ev.event_id, exc)
            log.warning("event handler lỗi", extra={"dx": {"consumer": consumer, "event_id": ev.event_id}})
            break
        with eng.begin() as conn:
            conn.execute(
                pg_insert(event_processed)
                .values(consumer=consumer, event_id=ev.event_id, processed_at=now_utc())
                .on_conflict_do_nothing()
            )
        last_ok = ev.event_id
        done += 1

    if last_ok:
        with eng.begin() as conn:
            stmt = pg_insert(event_offsets).values(consumer=consumer, last_event_id=last_ok, updated_at=now_utc())
            conn.execute(
                stmt.on_conflict_do_update(
                    index_elements=[event_offsets.c.consumer],
                    set_={"last_event_id": stmt.excluded.last_event_id, "updated_at": stmt.excluded.updated_at},
                    where=event_offsets.c.last_event_id < stmt.excluded.last_event_id,
                )
            )
    return done


def _record_failure(eng: Engine, consumer: str, event_id: str, exc: Exception) -> None:
    with eng.begin() as conn:
        stmt = pg_insert(event_dead_letters).values(
            consumer=consumer, event_id=event_id, attempts=1, last_error=type(exc).__name__, updated_at=now_utc()
        )
        conn.execute(
            stmt.on_conflict_do_update(
                index_elements=[event_dead_letters.c.consumer, event_dead_letters.c.event_id],
                set_={
                    "attempts": event_dead_letters.c.attempts + 1,
                    "last_error": stmt.excluded.last_error,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
        )
        conn.execute(
            update(event_dead_letters)
            .where(
                event_dead_letters.c.consumer == consumer,
                event_dead_letters.c.event_id == event_id,
                event_dead_letters.c.attempts >= MAX_ATTEMPTS,
            )
            .values(dead=True)
        )


def dead_letters(consumer: str, engine: Engine | None = None) -> list[str]:
    eng = engine or get_engine()
    with eng.connect() as conn:
        return [
            r[0]
            for r in conn.execute(
                select(event_dead_letters.c.event_id).where(
                    event_dead_letters.c.consumer == consumer, event_dead_letters.c.dead.is_(True)
                )
            )
        ]
