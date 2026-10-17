"""hãng vận chuyển (FR-ING-09)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-17 10:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ts() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "carrier_events",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("carrier", sa.Text(), nullable=False),
        sa.Column("waybill", sa.Text(), nullable=False),
        sa.Column("client_order_code", sa.Text(), nullable=True),
        sa.Column("status_raw", sa.Text(), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shipping_fee", sa.Numeric(18, 2), nullable=True),
        sa.Column("cod_amount", sa.Numeric(18, 2), nullable=True),
        *_ts(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "carrier", "waybill", "status_raw", "event_at", name="uq_carrier_events"),
    )
    op.create_index("ix_carrier_events_tenant", "carrier_events", ["tenant_id", "carrier", "waybill"])
    op.create_table(
        "carrier_files",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("carrier", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="received", nullable=False),
        sa.Column("rows_loaded", sa.Integer(), nullable=True),
        sa.Column("error_message_vi", sa.Text(), nullable=True),
        sa.Column("uploaded_by", sa.Text(), nullable=True),
        *_ts(),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status in ('received', 'loaded', 'rejected')", name="ck_carrier_files_status"),
    )


def downgrade() -> None:
    op.drop_table("carrier_files")
    op.drop_index("ix_carrier_events_tenant", table_name="carrier_events")
    op.drop_table("carrier_events")
