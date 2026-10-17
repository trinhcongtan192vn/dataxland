"""Schema Postgres của control plane (spec 05 §2). Alembic tạo bảng từ `Base.metadata` và `events_metadata`.

ID là ULID dạng chuỗi trừ khi ghi khác. Mọi bảng có `created_at`, `updated_at` (`timestamptz`).
Không bảng nào chứa thông tin cá nhân người mua dạng gốc (FR-AUTH-05). Email trong `health_checks` là email
của khách tiềm năng tự nhập, không phải người mua.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from dx_common.ids import new_ulid


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSONB, list[Any]: JSONB}


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def _id() -> Mapped[str]:
    return mapped_column(Text, primary_key=True, default=new_ulid)


# --------------------------------------------------------------------------- 2.1 Danh tính và quyền


class Tenant(Timestamps, Base):
    __tablename__ = "tenants"
    tenant_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    pack: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    bootstrap_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class User(Timestamps, Base):
    __tablename__ = "users"
    id: Mapped[str] = _id()
    firebase_uid: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    staff_role: Mapped[str | None] = mapped_column(Text)
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    __table_args__ = (
        CheckConstraint("staff_role is null or staff_role in ('data_lead', 'engineer')", name="ck_users_staff_role"),
        Index("ix_users_email", "email"),
    )


class Membership(Timestamps, Base):
    __tablename__ = "memberships"
    id: Mapped[str] = _id()
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(Text, ForeignKey("tenants.tenant_id"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    metric_allowlist: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    invited_by: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_memberships_user_tenant"),
        CheckConstraint("role in ('owner', 'member')", name="ck_memberships_role"),
    )


class Invitation(Timestamps, Base):
    __tablename__ = "invitations"
    id: Mapped[str] = _id()
    tenant_id: Mapped[str] = mapped_column(Text, ForeignKey("tenants.tenant_id"), nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    metric_allowlist: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    invited_by: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Partner(Timestamps, Base):
    __tablename__ = "partners"
    partner_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    contact_email: Mapped[str | None] = mapped_column(Text)


class PartnerUser(Timestamps, Base):
    __tablename__ = "partner_users"
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    partner_id: Mapped[str] = mapped_column(Text, ForeignKey("partners.partner_id"), primary_key=True)


class PartnerGrant(Timestamps, Base):
    __tablename__ = "partner_grants"
    id: Mapped[str] = _id()
    tenant_id: Mapped[str] = mapped_column(Text, ForeignKey("tenants.tenant_id"), nullable=False)
    partner_id: Mapped[str] = mapped_column(Text, ForeignKey("partners.partner_id"), nullable=False)
    granted_by: Mapped[str | None] = mapped_column(Text)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        Index(
            "uq_partner_grants_active",
            "tenant_id",
            "partner_id",
            unique=True,
            postgresql_where=text("revoked_at is null"),
        ),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[str] = _id()
    actor_user_id: Mapped[str | None] = mapped_column(Text)
    actor_service: Mapped[str | None] = mapped_column(Text)
    tenant_id: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (Index("ix_audit_log_tenant_at", "tenant_id", "at"),)


# --------------------------------------------------------------------------- 2.2 Nhập liệu


class ProductCost(Timestamps, Base):
    __tablename__ = "product_costs"
    id: Mapped[str] = _id()
    tenant_id: Mapped[str] = mapped_column(Text, ForeignKey("tenants.tenant_id"), nullable=False)
    seller_sku: Mapped[str] = mapped_column(Text, nullable=False)
    unit_cost_vnd: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("unit_cost_vnd >= 0", name="ck_product_costs_nonneg"),
        Index(
            "uq_product_costs_active",
            "tenant_id",
            "seller_sku",
            "valid_from",
            unique=True,
            postgresql_where=text("deleted_at is null"),
        ),
    )


class AdBudget(Timestamps, Base):
    __tablename__ = "ad_budgets"
    id: Mapped[str] = _id()
    tenant_id: Mapped[str] = mapped_column(Text, ForeignKey("tenants.tenant_id"), nullable=False)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    budget_vnd: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # FR-INP-05: trống = ngân sách cả nền tảng; có giá trị = ngân sách một chiến dịch (ADR 0002 #55).
    campaign_id: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("budget_vnd >= 0", name="ck_ad_budgets_nonneg"),
        CheckConstraint("extract(day from month) = 1", name="ck_ad_budgets_month_first"),
        Index(
            "uq_ad_budgets_active",
            "tenant_id",
            "platform",
            "month",
            text("coalesce(campaign_id, '')"),
            unique=True,
            postgresql_where=text("deleted_at is null"),
        ),
    )


class UploadJob(Timestamps, Base):
    __tablename__ = "upload_jobs"
    id: Mapped[str] = _id()
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    rows_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_ok: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_error: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    created_by: Mapped[str | None] = mapped_column(Text)


# --------------------------------------------------------------------------- Spec 04: thông báo, vận hành


class Notification(Timestamps, Base):
    __tablename__ = "notifications"
    id: Mapped[str] = _id()
    event_id: Mapped[str] = mapped_column(Text, nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_key: Mapped[str] = mapped_column(Text, nullable=False)
    audience: Mapped[str] = mapped_column(Text, nullable=False, server_default="team")
    template: Mapped[str] = mapped_column(Text, nullable=False)
    template_version: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_code: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    report_recipient_id: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("event_id", "channel", "recipient_key", name="uq_notifications_event_channel_recipient"),
        CheckConstraint("status in ('pending', 'sent', 'failed')", name="ck_notifications_status"),
        Index("ix_notifications_pending", "status", "next_attempt_at"),
    )


class NotificationGroup(Base):
    """Gộp cảnh báo team: cùng (tenant_id, type, reason) trong 6 giờ chỉ gửi một tin (spec 04 §5.4)."""

    __tablename__ = "notification_groups"
    group_key: Mapped[str] = mapped_column(Text, primary_key=True)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    suppressed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ChannelHealth(Base):
    """Trạng thái kết nối của kênh, để báo team khi Telegram lỗi liên tục 30 phút (spec 04 §5.4)."""

    __tablename__ = "channel_health"
    channel: Mapped[str] = mapped_column(Text, primary_key=True)
    failing_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PipelineRun(Timestamps, Base):
    __tablename__ = "pipeline_runs"
    run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    job: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_step: Mapped[str | None] = mapped_column(Text)
    blocking_failures: Mapped[list[Any] | None] = mapped_column(JSONB)
    steps: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    triage_md: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("status in ('running', 'success', 'blocked', 'failed')", name="ck_pipeline_runs_status"),
        Index("ix_pipeline_runs_tenant_started", "tenant_id", "started_at"),
    )


class SourceSync(Timestamps, Base):
    __tablename__ = "source_syncs"
    id: Mapped[str] = _id()
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(Text)
    last_error_code: Mapped[str | None] = mapped_column(Text)
    rows_loaded: Mapped[int | None] = mapped_column(BigInteger)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("tenant_id", "source", "account_id", name="uq_source_syncs"),)


class ErasureLog(Timestamps, Base):
    __tablename__ = "erasure_log"
    id: Mapped[str] = _id()
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    identifier_hash: Mapped[str] = mapped_column(Text, nullable=False)
    rows_affected: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    operator: Mapped[str] = mapped_column(Text, nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


# --------------------------------------------------------------------------- Spec 03: chỉ số


class MetricQuery(Base):
    __tablename__ = "metric_queries"
    query_id: Mapped[str] = mapped_column(Text, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[str | None] = mapped_column(Text)
    caller: Mapped[str] = mapped_column(Text, nullable=False)
    metrics: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    dimensions: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    time_from: Mapped[date | None] = mapped_column(Date)
    time_to: Mapped[date | None] = mapped_column(Date)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MetricAnomaly(Base):
    """Khóa chống phát trùng `metric.anomaly` theo (tenant_id, metric, grain, period) (spec 03 §8)."""

    __tablename__ = "metric_anomalies"
    tenant_id: Mapped[str] = mapped_column(Text, primary_key=True)
    metric: Mapped[str] = mapped_column(Text, primary_key=True)
    grain: Mapped[str] = mapped_column(Text, primary_key=True)
    period: Mapped[str] = mapped_column(Text, primary_key=True)
    event_id: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[float | None] = mapped_column(Numeric)
    baseline: Mapped[float | None] = mapped_column(Numeric)
    diff_pct: Mapped[float] = mapped_column(Numeric, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# --------------------------------------------------------------------------- Spec 06: báo cáo, quyết định


class Report(Timestamps, Base):
    __tablename__ = "reports"
    id: Mapped[str] = _id()
    tenant_id: Mapped[str] = mapped_column(Text, ForeignKey("tenants.tenant_id"), nullable=False)
    pack: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    insight_md: Mapped[str | None] = mapped_column(Text)
    actions: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    insight_draft_md: Mapped[str | None] = mapped_column(Text)
    actions_draft: Mapped[list[Any] | None] = mapped_column(JSONB)
    data_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    run_id: Mapped[str | None] = mapped_column(Text)
    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    template_version: Mapped[str | None] = mapped_column(Text)
    superseded_by: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint(
            "status in ('draft', 'approved', 'sent', 'partially_sent', 'failed', 'superseded')",
            name="ck_reports_status",
        ),
        Index(
            "uq_reports_tenant_period_active",
            "tenant_id",
            "period_start",
            unique=True,
            postgresql_where=text("status <> 'superseded'"),
        ),
    )


class ReportRecipient(Timestamps, Base):
    __tablename__ = "report_recipients"
    id: Mapped[str] = _id()
    report_id: Mapped[str] = mapped_column(Text, ForeignKey("reports.id"), nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_key: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[str | None] = mapped_column(Text)
    telegram_link_id: Mapped[str | None] = mapped_column(Text)
    open_token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)  # hash SHA-256 của token
    __table_args__ = (UniqueConstraint("report_id", "channel", "recipient_key", name="uq_report_recipients"),)


class ReportOpen(Timestamps, Base):
    __tablename__ = "report_opens"
    id: Mapped[str] = _id()
    recipient_id: Mapped[str | None] = mapped_column(Text, ForeignKey("report_recipients.id"))
    report_id: Mapped[str] = mapped_column(Text, ForeignKey("reports.id"), nullable=False)
    user_id: Mapped[str | None] = mapped_column(Text)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    via: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        CheckConstraint("via in ('email_link', 'telegram_button', 'portal')", name="ck_report_opens_via"),
    )


class Decision(Timestamps, Base):
    __tablename__ = "decisions"
    id: Mapped[str] = _id()
    tenant_id: Mapped[str] = mapped_column(Text, ForeignKey("tenants.tenant_id"), nullable=False)
    decided_on: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    detail_md: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str] = mapped_column(Text, nullable=False)
    metric: Mapped[str] = mapped_column(Text, nullable=False)
    metric_version: Mapped[str] = mapped_column(Text, nullable=False)
    dimension_filter: Mapped[list[Any] | None] = mapped_column(JSONB)
    baseline_window: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_value: Mapped[Decimal | None] = mapped_column(Numeric)
    target_value: Mapped[Decimal | None] = mapped_column(Numeric)
    remeasure_on: Mapped[date] = mapped_column(Date, nullable=False)
    after_value: Mapped[Decimal | None] = mapped_column(Numeric)
    after_measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    conclusion: Mapped[str | None] = mapped_column(Text)
    conclusion_md: Mapped[str | None] = mapped_column(Text)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("baseline_window in ('last_7_days', 'last_28_days')", name="ck_decisions_window"),
        CheckConstraint(
            "conclusion is null or conclusion in ('achieved', 'not_achieved', 'inconclusive')",
            name="ck_decisions_conclusion",
        ),
    )


# --------------------------------------------------------------------------- Spec 08: Telegram


class TelegramLinkCode(Timestamps, Base):
    __tablename__ = "telegram_link_codes"
    id: Mapped[str] = _id()
    code_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    metric_scope: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    __table_args__ = (CheckConstraint("kind in ('private', 'group')", name="ck_tg_codes_kind"),)


class TelegramLink(Timestamps, Base):
    __tablename__ = "telegram_links"
    id: Mapped[str] = _id()
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_type: Mapped[str] = mapped_column(Text, nullable=False)
    chat_title: Mapped[str | None] = mapped_column(Text)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    metric_scope: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("chat_type in ('private', 'group', 'supergroup')", name="ck_tg_links_chat_type"),
        CheckConstraint("status in ('active', 'revoked')", name="ck_tg_links_status"),
        Index("uq_tg_links_active", "chat_id", "tenant_id", unique=True, postgresql_where=text("status = 'active'")),
    )


class TelegramRate(Base):
    """Cửa sổ trượt theo chat cho lệnh, câu hỏi AI, mã sai (spec 08 §6, §3.2)."""

    __tablename__ = "telegram_rate"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (Index("ix_telegram_rate_key_kind_at", "key", "kind", "at"),)


# --------------------------------------------------------------------------- Spec 07: kiểm tra sức khỏe


class HealthCheck(Timestamps, Base):
    __tablename__ = "health_checks"
    check_id: Mapped[str] = mapped_column(Text, primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    shop_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="uploaded")
    consent_version: Mapped[str] = mapped_column(Text, nullable=False)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consent_convert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_token_hash: Mapped[str | None] = mapped_column(Text, unique=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    access_token_hash: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    funnel_counts: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reviewer_notes_md: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    converted_tenant_id: Mapped[str | None] = mapped_column(Text)
    ip_hash: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint(
            "status in ('uploaded', 'verified', 'processing', 'ready_for_review', 'approved', 'failed', 'expired',"
            " 'converted')",
            name="ck_health_checks_status",
        ),
    )


class HealthCheckFile(Timestamps, Base):
    __tablename__ = "health_check_files"
    id: Mapped[str] = _id()
    check_id: Mapped[str] = mapped_column(Text, ForeignKey("health_checks.check_id"), nullable=False)
    declared_kind: Mapped[str] = mapped_column(Text, nullable=False)
    detected_kind: Mapped[str | None] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    gcs_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="received")
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message_vi: Mapped[str | None] = mapped_column(Text)
    date_from: Mapped[date | None] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)
    rows_loaded: Mapped[int | None] = mapped_column(Integer)


# --------------------------------------------------------------------------- Spec 05 §6.7, §6.9, §8


class OAuthState(Timestamps, Base):
    __tablename__ = "oauth_states"
    state_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FxManualRate(Timestamps, Base):
    __tablename__ = "fx_manual_rates"
    id: Mapped[str] = _id()
    date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    rate_vnd: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    created_by: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("date", "currency", name="uq_fx_manual_rates"),
        CheckConstraint("rate_vnd > 0", name="ck_fx_manual_positive"),
    )


class RateCounter(Base):
    """Bộ đếm theo ô 10 giây cho giới hạn tần suất theo người dùng (spec 05 §8)."""

    __tablename__ = "rate_counters"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# --------------------------------------------------------------------------- Spec 09, 10 (GĐ2)


class MetricRequest(Timestamps, Base):
    __tablename__ = "metric_requests"
    id: Mapped[str] = _id()
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    description_vi: Mapped[str] = mapped_column(Text, nullable=False)
    description_key: Mapped[str] = mapped_column(Text, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="new")
    __table_args__ = (
        UniqueConstraint("tenant_id", "description_key", name="uq_metric_requests_key"),
        CheckConstraint("status in ('new', 'planned', 'done', 'declined')", name="ck_metric_requests_status"),
    )


class AskLog(Timestamps, Base):
    __tablename__ = "ask_logs"
    id: Mapped[str] = _id()
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[str | None] = mapped_column(Text)
    telegram_link_id: Mapped[str | None] = mapped_column(Text)
    conversation_id: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    question_masked: Mapped[str] = mapped_column(Text, nullable=False)
    answer_vi: Mapped[str | None] = mapped_column(Text)
    tool_calls: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    citations: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    refused_reason: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    feedback: Mapped[str | None] = mapped_column(Text)
    cache_key: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        Index("ix_ask_logs_conv", "conversation_id", "created_at"),
        Index("ix_ask_logs_cache", "cache_key"),
    )


class IdentityMatch(Timestamps, Base):
    __tablename__ = "identity_matches"
    id: Mapped[str] = _id()
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    entity: Mapped[str] = mapped_column(Text, nullable=False)
    left: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    right: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    pair_key: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    reason_vi: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_id: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("tenant_id", "entity", "pair_key", name="uq_identity_matches_pair"),
        CheckConstraint("status in ('proposed', 'approved', 'rejected', 'undone')", name="ck_identity_matches_status"),
    )


class TenantCost(Timestamps, Base):
    __tablename__ = "tenant_costs"
    id: Mapped[str] = _id()
    month: Mapped[date] = mapped_column(Date, nullable=False)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    item: Mapped[str] = mapped_column(Text, nullable=False)
    amount_vnd: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    __table_args__ = (UniqueConstraint("month", "tenant_id", "item", name="uq_tenant_costs"),)


class TenantHours(Timestamps, Base):
    __tablename__ = "tenant_hours"
    id: Mapped[str] = _id()
    month: Mapped[date] = mapped_column(Date, nullable=False)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("month", "tenant_id", name="uq_tenant_hours"),)


# --------------------------------------------------------------------------- Hãng vận chuyển (FR-ING-09, ADR 0005)


class CarrierEvent(Timestamps, Base):
    """Trạng thái vận đơn hãng đẩy qua webhook (GHN, GHTK). Chỉ trường vận đơn, không có thông tin người nhận."""

    __tablename__ = "carrier_events"
    id: Mapped[str] = _id()
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    carrier: Mapped[str] = mapped_column(Text, nullable=False)
    waybill: Mapped[str] = mapped_column(Text, nullable=False)
    client_order_code: Mapped[str | None] = mapped_column(Text)
    status_raw: Mapped[str] = mapped_column(Text, nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    shipping_fee: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    cod_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    __table_args__ = (
        UniqueConstraint("tenant_id", "carrier", "waybill", "status_raw", "event_at", name="uq_carrier_events"),
        Index("ix_carrier_events_tenant", "tenant_id", "carrier", "waybill"),
    )


class CarrierFile(Timestamps, Base):
    """File đối soát của hãng khách tải lên (J&T)."""

    __tablename__ = "carrier_files"
    id: Mapped[str] = _id()
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    carrier: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="received")
    rows_loaded: Mapped[int | None] = mapped_column(Integer)
    error_message_vi: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (CheckConstraint("status in ('received', 'loaded', 'rejected')", name="ck_carrier_files_status"),)
