"""ngân sách theo chiến dịch (FR-INP-05)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-17 09:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ad_budgets", sa.Column("campaign_id", sa.Text(), nullable=True))
    op.drop_index("uq_ad_budgets_active", table_name="ad_budgets", postgresql_where=sa.text("deleted_at is null"))
    op.create_index(
        "uq_ad_budgets_active",
        "ad_budgets",
        ["tenant_id", "platform", "month", sa.text("coalesce(campaign_id, '')")],
        unique=True,
        postgresql_where=sa.text("deleted_at is null"),
    )


def downgrade() -> None:
    op.drop_index("uq_ad_budgets_active", table_name="ad_budgets", postgresql_where=sa.text("deleted_at is null"))
    op.create_index(
        "uq_ad_budgets_active",
        "ad_budgets",
        ["tenant_id", "platform", "month"],
        unique=True,
        postgresql_where=sa.text("deleted_at is null"),
    )
    op.drop_column("ad_budgets", "campaign_id")
