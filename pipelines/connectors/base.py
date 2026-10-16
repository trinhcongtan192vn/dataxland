"""Khung chung cho connector (spec 01 §2)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from dx_common.tenants import SourceConfig, TenantConfig

Reason = Literal["auth_revoked", "rate_limited", "api_error"]


class SourceError(Exception):
    """Lỗi của một nguồn: dừng nguồn đó và phát `sync.failed` với `reason` (spec 01 §2.1)."""

    def __init__(self, reason: Reason, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


@dataclass
class SyncContext:
    warehouse: Any
    raw_dataset: str
    run_id: str
    now: datetime
    history: bool = False  # lần chạy đầu: nạp lịch sử (FR-ING-05)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SyncOutcome:
    rows_loaded: int
    status: Literal["success", "skipped"] = "success"
    tables: dict[str, int] = field(default_factory=dict)
    note: str | None = None


class Connector(Protocol):
    def __call__(self, tenant: TenantConfig, source: SourceConfig, ctx: SyncContext) -> SyncOutcome: ...


def record_hash(rec: dict[str, Any]) -> str:
    body = {k: v for k, v in rec.items() if not k.startswith("_dx_") and not k.startswith("_dlt_")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def with_contract(rec: dict[str, Any], account: str, loaded_at: datetime) -> dict[str, Any]:
    """Thêm ba cột bắt buộc của hợp đồng raw (spec 01 §1)."""
    out = dict(rec)
    out["_dx_loaded_at"] = loaded_at
    out["_dx_source_account"] = account
    out["_dx_record_hash"] = record_hash(rec)
    return out
