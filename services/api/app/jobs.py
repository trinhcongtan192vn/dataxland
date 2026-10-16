"""Job phụ chạy trong worker nền: báo team sự kiện chết, dọn bộ đếm tần suất."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Notification
from app.notify.dispatcher import team_recipients
from app.notify.render import render
from app.ratelimit import cleanup
from dx_common.events.tables import event_dead_letters, events
from dx_common.ids import new_ulid
from dx_common.timeutil import now_utc

DbFactory = Callable[[], AbstractContextManager[Session]]


def alert_dead_letters(db: Session) -> int:
    """Sự kiện xử lý lỗi quá 5 lần thì báo team một lần (spec 04 §4.2)."""
    rows = db.execute(
        select(event_dead_letters.c.consumer, event_dead_letters.c.event_id, events.c.type)
        .join(events, events.c.event_id == event_dead_letters.c.event_id)
        .where(event_dead_letters.c.dead.is_(True))
    ).all()
    n = 0
    for consumer, event_id, ev_type in rows:
        msg = render("dead_letter", {"consumer": consumer, "event_id": event_id, "event_type": ev_type})
        for r in team_recipients():
            ch = "email" if "@" in r.address else "telegram"
            res = db.execute(
                insert(Notification)
                .values(
                    id=new_ulid(),
                    event_id=f"dead:{consumer}:{event_id}",
                    channel=ch,
                    recipient_key=r.key,
                    audience="team",
                    template=msg.template,
                    template_version=msg.template_version,
                    message=msg.to_json(),
                    status="pending",
                    attempts=0,
                    next_attempt_at=now_utc(),
                )
                .on_conflict_do_nothing(index_elements=["event_id", "channel", "recipient_key"])
            )
            n += getattr(res, "rowcount", 0) or 0
    return n


def extra_jobs(db_factory: DbFactory) -> dict[str, Any]:
    with db_factory() as db:
        dead = alert_dead_letters(db)
        cleanup(db)
    return {"dead_letter_alerts": dead}
