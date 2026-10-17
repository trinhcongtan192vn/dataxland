"""Model Pydantic của cấu hình khách (spec 04 §1.1). Trường không ghi lấy mặc định theo gói."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TENANT_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,30}$")

SALES_SOURCES = frozenset({"shopee", "tiktok_shop", "lazada", "amazon_seller"})
AD_SOURCES = frozenset({"meta_ads", "tiktok_ads", "google_ads", "amazon_ads"})
AMAZON_SOURCES = frozenset({"amazon_ads", "amazon_seller"})
WINDSOR_SOURCES = AD_SOURCES | {"amazon_seller"}
DLT_SOURCES = frozenset({"shopee", "tiktok_shop", "lazada", "portal", "ghn", "ghtk", "jnt"})
KNOWN_SOURCES = SALES_SOURCES | AD_SOURCES | DLT_SOURCES

PACK_DEFAULTS: dict[str, dict[str, Any]] = {
    "seller": {"sync": "0 */6 * * *", "freshness_hours": 8},
    "agency": {"sync": "0 */3 * * *", "freshness_hours": 5},
}

Pack = Literal["seller", "agency"]
Status = Literal["trial", "active", "paused", "offboarding"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Warehouse(_Base):
    provider: Literal["bigquery", "duckdb"] = "bigquery"
    project: str = "dataxland-prod"
    location: str = "asia-southeast1"


class SourceConfig(_Base):
    type: str
    connector: Literal["dlt", "windsor"]
    account_id: str | None = None
    secret_ref: str | None = None
    enabled: bool = True

    @field_validator("type")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in KNOWN_SOURCES:
            raise ValueError(f"nguồn không hỗ trợ: {v}")
        return v


class Schedule(_Base):
    sync: str | None = None
    weekly_report: str = "MON 07:00"


def _pct_map(v: Any) -> dict[str, float]:
    if v is None:
        return {"default": 1.0}
    if isinstance(v, (int, float)):
        return {"default": float(v)}
    if isinstance(v, dict):
        out = {str(k): float(x) for k, x in v.items()}
        out.setdefault("default", 1.0)
        return out
    raise ValueError("phải là số hoặc map")


def _days_map(v: Any) -> dict[str, int]:
    if v is None:
        return {"default": 14}
    if isinstance(v, int):
        return {"default": v}
    if isinstance(v, dict):
        out = {str(k): int(x) for k, x in v.items()}
        out.setdefault("default", 14)
        return out
    raise ValueError("phải là số hoặc map")


class Quality(_Base):
    freshness_hours: int | None = None
    reconcile_tolerance_pct: dict[str, float] = Field(default_factory=lambda: {"default": 1.0})
    provisional_window_days: dict[str, int] = Field(default_factory=lambda: {"default": 14})

    @field_validator("reconcile_tolerance_pct", mode="before")
    @classmethod
    def _tol(cls, v: Any) -> dict[str, float]:
        return _pct_map(v)

    @field_validator("provisional_window_days", mode="before")
    @classmethod
    def _prov(cls, v: Any) -> dict[str, int]:
        return _days_map(v)


class Attention(_Base):
    overspend_pct: float = 15
    roas_drop_pct: float = 25
    platform_gap_pct: float = 50


class Features(_Base):
    identity: bool = False


class Identity(_Base):
    suggest_threshold: float = 0.7


class Overrides(_Base):
    status_map: str | None = None


class Notify(_Base):
    channels: list[Literal["telegram", "email"]] = Field(
        default_factory=lambda: list[Literal["telegram", "email"]](["telegram", "email"])
    )
    email: list[str] = Field(default_factory=list)
    anomaly_alerts: bool = True


class TenantConfig(_Base):
    tenant_id: str
    name: str
    status: Status = "active"
    pack: Pack
    warehouse: Warehouse = Field(default_factory=Warehouse)
    sources: list[SourceConfig] = Field(default_factory=list)
    schedule: Schedule = Field(default_factory=Schedule)
    quality: Quality = Field(default_factory=Quality)
    cost_allocation: Literal["by_revenue", "by_order", "none"] = "by_revenue"
    attention: Attention = Field(default_factory=Attention)
    features: Features = Field(default_factory=Features)
    identity: Identity = Field(default_factory=Identity)
    overrides: Overrides = Field(default_factory=Overrides)
    notify: Notify = Field(default_factory=Notify)
    benchmark_opt_in: bool = False
    partners: list[str] = Field(default_factory=list)

    @field_validator("tenant_id")
    @classmethod
    def _tid(cls, v: str) -> str:
        if not TENANT_ID_RE.match(v):
            raise ValueError("tenant_id phải khớp [a-z][a-z0-9_]{2,30}")
        return v

    @model_validator(mode="after")
    def _defaults_and_rules(self) -> TenantConfig:
        d = PACK_DEFAULTS[self.pack]
        if self.schedule.sync is None:
            self.schedule.sync = d["sync"]
        if self.quality.freshness_hours is None:
            self.quality.freshness_hours = d["freshness_hours"]
        if not any(s.type == "portal" for s in self.sources):
            self.sources.append(SourceConfig(type="portal", connector="dlt"))
        for s in self.sources:
            if s.connector == "dlt" and s.type != "portal" and not s.secret_ref:
                raise ValueError(f"nguồn {s.type}: secret_ref bắt buộc với connector dlt")
            if s.connector == "windsor" and s.type not in WINDSOR_SOURCES:
                raise ValueError(f"nguồn {s.type} không nạp qua Windsor")
        if self.pack == "agency" and not any(s.type in AD_SOURCES for s in self.sources):
            raise ValueError("gói agency cần ít nhất một nguồn quảng cáo")
        _validate_cron(self.schedule.sync or "")
        _validate_weekly(self.schedule.weekly_report)
        return self

    # Tiện ích dùng chung --------------------------------------------------

    @property
    def dataset_prefix(self) -> str:
        from dx_common.tenants.naming import dataset_prefix

        return dataset_prefix(self.tenant_id)

    def enabled_sources(self) -> list[SourceConfig]:
        return [s for s in self.sources if s.enabled]

    def source_types(self) -> list[str]:
        return sorted({s.type for s in self.enabled_sources()})

    def has_amazon(self) -> bool:
        return any(s.type in AMAZON_SOURCES for s in self.enabled_sources())

    def ad_platforms(self) -> list[str]:
        return sorted({s.type for s in self.enabled_sources() if s.type in AD_SOURCES})

    def dbt_vars(self, dataset_prefix: str | None = None) -> dict[str, Any]:
        """Biến dbt theo spec 02 §1.1."""
        return {
            "tenant_id": self.tenant_id,
            "pack": self.pack,
            "sources": self.source_types(),
            "cost_allocation": self.cost_allocation,
            "freshness_hours": self.quality.freshness_hours,
            "reconcile_tolerance_pct": self.quality.reconcile_tolerance_pct,
            "provisional_window_days": self.quality.provisional_window_days,
            "dataset_prefix": dataset_prefix or self.dataset_prefix,
        }


class Partner(_Base):
    partner_id: str
    name: str
    contact_email: str


_WEEKDAYS = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}


def _validate_cron(expr: str) -> None:
    from croniter import croniter  # type: ignore[import-untyped]

    if not croniter.is_valid(expr):
        raise ValueError(f"schedule.sync không phải cron hợp lệ: {expr!r}")


def _validate_weekly(expr: str) -> None:
    parse_weekly(expr)


def parse_weekly(expr: str) -> tuple[int, int, int]:
    """`MON 07:00` → (weekday, hour, minute)."""
    try:
        day, hm = expr.strip().upper().split()
        h, m = hm.split(":")
        return _WEEKDAYS[day], int(h), int(m)
    except (ValueError, KeyError) as exc:
        raise ValueError(f"schedule.weekly_report không hợp lệ: {expr!r}") from exc
