"""Bảng `events`, `event_offsets`, `event_processed`, `event_dead_letters` (spec 04 §4.1).

Alembic của `services/api` tạo các bảng này từ `metadata` ở đây.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

events = Table(
    "events",
    metadata,
    Column("event_id", Text, primary_key=True),
    Column("type", Text, nullable=False),
    Column("version", Integer, nullable=False, server_default="1"),
    Column("tenant_id", Text),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("producer", Text, nullable=False),
    Column("payload", JSONB, nullable=False),
    Index("ix_events_type_event_id", "type", "event_id"),
)

event_offsets = Table(
    "event_offsets",
    metadata,
    Column("consumer", Text, primary_key=True),
    Column("last_event_id", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

event_processed = Table(
    "event_processed",
    metadata,
    Column("consumer", Text, nullable=False),
    Column("event_id", Text, nullable=False),
    Column("processed_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("consumer", "event_id"),
)

# Đếm số lần xử lý lỗi; `dead = true` khi quá 5 lần (spec 04 §4.2).
event_dead_letters = Table(
    "event_dead_letters",
    metadata,
    Column("consumer", Text, nullable=False),
    Column("event_id", Text, nullable=False),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("last_error", Text),
    Column("dead", Boolean, nullable=False, server_default="false"),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("consumer", "event_id"),
)
