"""Truy cập Postgres control plane."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import MetaData
from sqlalchemy.orm import Session

from app.db.models import Base
from dx_common.db import session_factory
from dx_common.events.tables import metadata as events_metadata

target_metadata: list[MetaData] = [Base.metadata, events_metadata]


def get_db() -> Iterator[Session]:
    """Dependency FastAPI: một session cho mỗi request, commit khi thành công."""
    session = session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
