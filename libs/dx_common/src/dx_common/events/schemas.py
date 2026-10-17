"""Model payload theo loại sự kiện (spec 04 §4.3, architecture §11.2)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class _P(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Empty(_P):
    pass


class SyncFailed(_P):
    run_id: str | None = None
    source: str | None = None
    reason: Literal[
        "auth_revoked",
        "rate_limited",
        "api_error",
        "windsor_stale",
        "override_invalid",
        "dbt_error",
        "swap_failed",
        "cube_refresh_failed",
    ]
    detail: str | None = None


class TransformFinished(_P):
    run_id: str
    data_as_of: str | None = None


class TestFailureRow(BaseModel):
    model_config = ConfigDict(extra="allow")


class TestFailure(_P):
    test: str
    severity: Literal["error", "warn"]
    rows: list[dict[str, Any]] = []


class TestFailed(_P):
    run_id: str
    failures: list[TestFailure]


class MetricAnomaly(_P):
    metric: str
    version: str
    grain: Literal["day", "week"]
    period: str
    value: float | None
    baseline: float | None
    diff_pct: float
    direction: Literal["good", "bad"]


class ReportReady(_P):
    report_id: str
    period: str


class TelegramLink(_P):
    link_id: str
    chat_type: str


class DecisionRef(_P):
    decision_id: str


class MetricReleased(_P):
    metric: str
    old_version: str | None
    new_version: str


class HealthCheckRef(_P):
    check_id: str


class InputsChanged(_P):
    kind: Literal["product_costs", "ad_budgets", "carrier_files"]


class MatchProposed(_P):
    match_id: str
    entity: Literal["product", "customer"]
    score: float


class PipelineRequested(_P):
    """Sự kiện nội bộ: yêu cầu chạy lại `tenant_pipeline` (spec 05 §6.9)."""

    requested_by: str | None = None
    full_refresh: bool = False
    reason: str | None = None


class IdentityChanged(_P):
    """Sự kiện nội bộ: cặp ghép đã duyệt thay đổi, cần dbt build lại (spec 10 §6)."""

    entity: str


class ConfigInvalid(_P):
    """Sự kiện nội bộ: file cấu hình khách lỗi khi đồng bộ (spec 04 §1.3)."""

    path: str
    errors: list[str]


class BootstrapRequired(_P):
    """Sự kiện nội bộ: khách mới cần chạy `ops/bootstrap_tenant.py` (spec 04 §1.3)."""


_MODELS: dict[str, type[BaseModel]] = {
    "tenant.created": Empty,
    "tenant.bootstrap_required": BootstrapRequired,
    "tenant.config_invalid": ConfigInvalid,
    "sync.failed": SyncFailed,
    "transform.finished": TransformFinished,
    "test.failed": TestFailed,
    "metric.anomaly": MetricAnomaly,
    "match.proposed": MatchProposed,
    "healthcheck.submitted": HealthCheckRef,
    "healthcheck.completed": HealthCheckRef,
    "healthcheck.failed": HealthCheckRef,
    "inputs.changed": InputsChanged,
    "report.ready": ReportReady,
    "report.built": ReportReady,
    "telegram.linked": TelegramLink,
    "telegram.unlinked": TelegramLink,
    "decision.logged": DecisionRef,
    "decision.remeasure_due": DecisionRef,
    "metric.released": MetricReleased,
    "pipeline.requested": PipelineRequested,
    "identity.changed": IdentityChanged,
}

EVENT_TYPES = frozenset(_MODELS)


def payload_model(event_type: str) -> type[BaseModel]:
    try:
        return _MODELS[event_type]
    except KeyError as exc:
        raise ValueError(f"Loại sự kiện không có trong danh mục: {event_type}") from exc
