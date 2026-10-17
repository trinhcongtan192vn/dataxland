"""Job `tenant_pipeline` cho một khách (FR-OPS-03, FR-DQ-04, spec 04 §3.2).

Các bước chạy theo thứ tự; bước lỗi thì các bước sau không chạy và hệ thống phát sự kiện tương ứng. Mỗi bước ghi
trạng thái qua `POST /v1/internal/runs` để màn hình vận hành đọc (spec 04 §6).

Khi có test chặn: không hoán đổi marts, không làm mới Cube, không phát `transform.finished`, không dựng báo cáo.
Dashboard tiếp tục đọc marts của lần chạy tốt trước (spec 04 §3.2, FR-DQ-04).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from connectors.base import SourceError, SyncContext
from connectors.registry import connector_for
from dx_common.config import get_settings
from dx_common.logging import get_logger, run_id_var, tenant_id_var
from dx_common.secrets import SecretNotFound, get_secret_store
from dx_common.tenants import TenantConfig
from dx_common.tenants.naming import pii_salt_secret
from dx_common.timeutil import iso_z, now_utc, today_vn
from dx_pipelines.api_client import Api
from dx_pipelines.cube import CubeLike
from dx_pipelines.dbt import DbtLike, DbtResult, blocking_failures, repo_root, warning_failures
from dx_pipelines.metadata import upload_run_metadata
from dx_pipelines.overrides import OverrideInvalid, load_overrides
from dx_pipelines.warehouse import Warehouse

log = get_logger(__name__)

STEPS = (
    "load_overrides",
    "sync_sources",
    "check_windsor_freshness",
    "resolve_identity",
    "dbt_build",
    "evaluate_tests",
    "swap_marts",
    "upload_run_metadata",
    "refresh_cube",
    "emit_finished",
    "detect_anomalies",
)
WARN_ONLY = frozenset({"upload_run_metadata", "detect_anomalies", "resolve_identity"})
PRODUCER = "s1-core"


class StepFailed(Exception):
    def __init__(self, reason: str, detail: str = "", source: str | None = None) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail
        self.source = source


class Blocked(Exception):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        super().__init__("blocked")
        self.failures = failures


@dataclass
class Services:
    api: Api
    warehouse: Warehouse
    dbt: DbtLike
    cube: CubeLike
    connector_for: Callable[..., Any] = connector_for
    upload_metadata: Callable[..., Any] = upload_run_metadata
    repo: Path = field(default_factory=repo_root)


@dataclass
class RunOutcome:
    run_id: str
    status: str  # success | blocked | failed
    steps: dict[str, str]
    failed_step: str | None = None
    failures: list[dict[str, Any]] = field(default_factory=list)
    data_as_of: datetime | None = None
    warnings: list[str] = field(default_factory=list)


class TenantPipeline:
    def __init__(
        self,
        tenant: TenantConfig,
        run_id: str,
        services: Services,
        *,
        history: bool = False,
        full_refresh: bool = False,
        select: list[str] | None = None,
        today: str | None = None,
    ) -> None:
        self.tenant = tenant
        self.run_id = run_id
        self.s = services
        self.history = history
        self.full_refresh = full_refresh
        self.select = select
        self.today = today
        self.prefix = tenant.dataset_prefix
        self.raw = f"{self.prefix}_raw"
        self.target_path = services.repo / "transform" / "target" / "runs" / tenant.tenant_id / run_id
        self.steps: dict[str, str] = {}
        self.started_at = now_utc()
        self.build_result: DbtResult | None = None
        self.freshness_result: DbtResult | None = None
        self.data_as_of: datetime | None = None
        self.warnings: list[str] = []
        self.source_status: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ chạy

    def run(self) -> RunOutcome:
        tenant_id_var.set(self.tenant.tenant_id)
        run_id_var.set(self.run_id)
        self._report("running")
        for step in STEPS:
            try:
                self.run_step(step)
            except StepFailed as exc:
                self._fail(step, exc)
                return RunOutcome(self.run_id, "failed", self.steps, failed_step=step, warnings=self.warnings)
            except Blocked as exc:
                self._block(step, exc.failures)
                return RunOutcome(
                    self.run_id, "blocked", self.steps, failed_step=step, failures=exc.failures, warnings=self.warnings
                )
        self._report("success", data_as_of=self.data_as_of)
        return RunOutcome(self.run_id, "success", self.steps, data_as_of=self.data_as_of, warnings=self.warnings)

    def run_step(self, step: str) -> None:
        self.steps[step] = "running"
        self._report("running", step=step, step_status="running")
        try:
            getattr(self, step)()
        except (StepFailed, Blocked):
            self.steps[step] = "failed"
            raise
        except Exception as exc:
            if step in WARN_ONLY:
                self.steps[step] = "warning"
                self.warnings.append(f"{step}: {type(exc).__name__}: {str(exc)[:200]}")
                log.warning("bước %s lỗi (chỉ cảnh báo): %s", step, type(exc).__name__)
                self._report("running", step=step, step_status="warning")
                return
            self.steps[step] = "failed"
            raise StepFailed(_DEFAULT_REASON.get(step, "api_error"), f"{type(exc).__name__}: {str(exc)[:300]}") from exc
        self.steps[step] = "success"
        self._report("running", step=step, step_status="success")

    # ------------------------------------------------------------------ các bước

    def _env(self) -> dict[str, str]:
        env = {"DX_TENANT_ID": self.tenant.tenant_id}
        try:
            env["DX_PII_SALT"] = get_secret_store().get(pii_salt_secret(self.tenant.tenant_id))
        except SecretNotFound:
            env["DX_PII_SALT"] = ""
        return env

    def _vars(self) -> dict[str, Any]:
        v = self.tenant.dbt_vars()
        v["today"] = self.today or today_vn().isoformat()
        v["run_id"] = self.run_id
        return v

    def load_overrides(self) -> None:
        try:
            load_overrides(self.tenant, self.s.repo, self.s.warehouse, self.raw)
        except OverrideInvalid as exc:
            raise StepFailed("override_invalid", str(exc)) from exc

    def sync_sources(self) -> None:
        ctx = SyncContext(
            warehouse=self.s.warehouse, raw_dataset=self.raw, run_id=self.run_id, now=now_utc(), history=self.history
        )
        for src in self.tenant.enabled_sources():
            conn = self.s.connector_for(src)
            if conn is None:
                continue
            try:
                out = conn(self.tenant, src, ctx)
            except SourceError as exc:
                self.source_status.append(
                    {
                        "source": src.type,
                        "account_id": src.account_id or "",
                        "status": "failed",
                        "error_code": exc.reason,
                    }
                )
                self._report("running", sources=self.source_status[-1:])
                raise StepFailed(exc.reason, exc.detail, source=src.type) from exc
            st = {
                "source": src.type,
                "account_id": src.account_id or "",
                "status": "success",
                "rows_loaded": out.rows_loaded,
            }
            self.source_status.append(st)
            self._report("running", sources=[st])

    def check_windsor_freshness(self) -> None:
        """Spec 01 §8.3: `max(_dx_loaded_at)` của từng bảng Windsor; quá `freshness_hours` thì lỗi."""
        limit = timedelta(hours=self.tenant.quality.freshness_hours or 8)
        tables = self.s.warehouse.list_tables(self.raw)
        stale: list[str] = []
        for src in self.tenant.enabled_sources():
            if src.connector != "windsor":
                continue
            mine = [t for t in tables if t.startswith(f"{src.type}__")]
            if not mine:
                stale.append(f"{src.type}: chưa có bảng")
                continue
            for t in mine:
                ts = self.s.warehouse.max_timestamp(self.raw, t, "_dx_loaded_at")
                age = now_utc() - ts if ts else None
                ok = ts is not None and age is not None and age <= limit
                st = {
                    "source": src.type,
                    "account_id": src.account_id or "",
                    "status": "success" if ok else "failed",
                    "error_code": None if ok else "windsor_stale",
                }
                self._report("running", sources=[st])
                if not ok:
                    stale.append(f"{t}: {'không có dữ liệu' if ts is None else f'cũ {age}'}")
        if stale:
            raise StepFailed("windsor_stale", "; ".join(stale)[:500], source="windsor")

    def resolve_identity(self) -> None:
        """Ghép định danh (spec 10 §1): khách bật `features.identity` hoặc bán trên hơn một kênh. Ghi `identity_map`
        trước dbt; gợi ý sản phẩm (có thể gọi Claude) tối đa một lần mỗi ngày. Lỗi chỉ cảnh báo."""
        sales = [t for t in self.tenant.source_types() if t in ("shopee", "tiktok_shop", "lazada", "amazon_seller")]
        if not (self.tenant.features.identity or len(sales) > 1):
            return
        from identity_worker.judge import anthropic_caller
        from identity_worker.worker import run as run_identity

        s = get_settings()
        call = anthropic_caller(s.anthropic_api_key, s.anthropic_model_agent) if s.anthropic_api_key else None
        stats = run_identity(
            self.tenant.tenant_id,
            self.tenant.dataset_prefix,
            sales,
            self.tenant.identity.suggest_threshold,
            self.s.warehouse,
            self.s.api,
            today_vn().isoformat(),
            call,
            self.run_id,
            suggest=None,
            publish_change=False,
        )
        log.info("identity: %s", stats)

    def dbt_build(self) -> None:
        env = self._env()
        self.freshness_result = self.s.dbt.freshness(self._vars(), self.target_path, env)
        # Unit test dbt chạy trong CI (`make test-dbt`), không cần chạy ở mỗi lần đồng bộ.
        self.build_result = self.s.dbt.build(
            self._vars(),
            self.target_path,
            env,
            full_refresh=self.full_refresh,
            select=self.select,
            exclude=["resource_type:unit_test"],
        )
        if self.build_result.runtime_error:
            raise StepFailed("dbt_error", _dbt_error_detail(self.build_result))

    def evaluate_tests(self) -> None:
        assert self.build_result is not None
        failures = blocking_failures(self.build_result, self.freshness_result)
        warns = warning_failures(self.build_result)
        self.warnings.extend(f"test cảnh báo: {w}" for w in warns)
        if failures:
            for f in failures:
                if not f["rows"]:
                    f["rows"] = self._failure_rows(f["test"])
            raise Blocked(failures)

    def _failure_rows(self, test_name: str) -> list[dict[str, Any]]:
        """Dòng lỗi của test đối soát (`store_failures: true`), tối đa 20 dòng mỗi test (spec 04 §3.2)."""
        audit = f"{self.prefix}_audit"
        try:
            if test_name not in self.s.warehouse.list_tables(audit):
                return []
            cols = [
                r[0]
                for r in self.s.warehouse.query(
                    "select column_name from information_schema.columns where table_schema = ? and table_name = ?"
                    " order by ordinal_position",
                    [audit, test_name],
                )
            ]
            rows = self.s.warehouse.query(f'select * from "{audit}"."{test_name}" limit 20')
        except Exception:
            return []
        out = []
        for r in rows:
            d = {
                c: (v.isoformat() if hasattr(v, "isoformat") else (float(v) if hasattr(v, "as_tuple") else v))
                for c, v in zip(cols, r, strict=False)
            }
            out.append(
                {k: d.get(k) for k in ("source", "date", "metric", "expected", "actual", "diff_pct") if k in d} or d
            )
        return out

    def swap_marts(self) -> None:
        res = self.s.dbt.run_operation("dx_swap_marts", {}, self._vars(), self.target_path, self._env())
        if not res.ok:
            raise StepFailed("swap_failed", res.stdout_tail[-400:])
        rows = self.s.warehouse.query(f'select max(data_as_of) from "{self.prefix}_marts"."mrt_common__data_status"')
        v = rows[0][0] if rows else None
        if v is not None:
            from datetime import UTC

            if isinstance(v, str):
                v = datetime.fromisoformat(v.replace("Z", "+00:00"))
            self.data_as_of = v if v.tzinfo else v.replace(tzinfo=UTC)

    def upload_run_metadata(self) -> None:
        self.s.upload_metadata(self.tenant.tenant_id, self.run_id, self.target_path)

    def refresh_cube(self) -> None:
        try:
            self.s.cube.refresh(self.tenant.tenant_id, self.prefix)
        except Exception as exc:
            raise StepFailed("cube_refresh_failed", f"{type(exc).__name__}: {str(exc)[:300]}") from exc

    def emit_finished(self) -> None:
        self.s.api.publish(
            "transform.finished",
            self.tenant.tenant_id,
            {"run_id": self.run_id, "data_as_of": iso_z(self.data_as_of) if self.data_as_of else None},
            PRODUCER,
        )

    def detect_anomalies(self) -> None:
        self.s.api.run_anomalies(self.tenant.tenant_id, self.run_id)

    # ------------------------------------------------------------------ báo trạng thái

    def _report(
        self,
        status: str,
        *,
        step: str | None = None,
        step_status: str | None = None,
        failed_step: str | None = None,
        blocking: list[dict[str, Any]] | None = None,
        data_as_of: datetime | None = None,
        sources: list[dict[str, Any]] | None = None,
    ) -> None:
        body: dict[str, Any] = {
            "run_id": self.run_id,
            "tenant_id": self.tenant.tenant_id,
            "job": "tenant_pipeline",
            "status": status,
            "started_at": iso_z(self.started_at),
        }
        if step:
            body["step"], body["step_status"] = step, step_status
        if failed_step:
            body["failed_step"] = failed_step
        if blocking is not None:
            body["blocking_failures"] = blocking
        if data_as_of:
            body["data_as_of"] = iso_z(data_as_of)
        if sources:
            body["sources"] = sources
        try:
            self.s.api.record_run(body)
        except Exception as exc:  # không để việc ghi trạng thái làm hỏng pipeline
            log.warning("không ghi được trạng thái chạy: %s", type(exc).__name__)

    def _fail(self, step: str, exc: StepFailed) -> None:
        self._report("failed", failed_step=step)
        self.s.api.publish(
            "sync.failed",
            self.tenant.tenant_id,
            {"run_id": self.run_id, "source": exc.source, "reason": exc.reason, "detail": exc.detail[:500]},
            PRODUCER,
        )

    def _block(self, step: str, failures: list[dict[str, Any]]) -> None:
        payload = [{"test": f["test"], "severity": "error", "rows": f.get("rows", [])[:20]} for f in failures]
        self._report("blocked", failed_step=step, blocking=payload)
        self.s.api.publish("test.failed", self.tenant.tenant_id, {"run_id": self.run_id, "failures": payload}, PRODUCER)


_DEFAULT_REASON = {
    "load_overrides": "override_invalid",
    "sync_sources": "api_error",
    "check_windsor_freshness": "windsor_stale",
    "dbt_build": "dbt_error",
    "evaluate_tests": "dbt_error",
    "swap_marts": "swap_failed",
    "refresh_cube": "cube_refresh_failed",
    "emit_finished": "api_error",
}


def _dbt_error_detail(res: DbtResult) -> str:
    errs = [
        f"{r.get('unique_id')}: {(r.get('message') or '')[:160]}"
        for r in res.run_results.get("results", [])
        if r.get("status") == "error" and not r.get("unique_id", "").startswith("test.")
    ]
    return "; ".join(errs)[:500] or res.stdout_tail[-500:]
