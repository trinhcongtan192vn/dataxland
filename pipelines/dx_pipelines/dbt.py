"""Gọi dbt cho một khách (spec 02 §1.1, spec 04 §3.2). Mỗi lần chạy có `target-path` riêng."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from dx_common.config import get_settings
from dx_common.logging import get_logger

log = get_logger(__name__)


@dataclass
class DbtResult:
    command: str
    returncode: int
    target_path: Path
    run_results: dict[str, Any] = field(default_factory=dict)
    sources: dict[str, Any] = field(default_factory=dict)
    stdout_tail: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def runtime_error(self) -> bool:
        """Lỗi chạy (không phải lỗi test): node không phải test bị lỗi, hoặc dbt không chạy được."""
        if self.returncode not in (0, 1):
            return True
        for r in self.run_results.get("results", []):
            if r.get("status") == "error" and not r.get("unique_id", "").startswith("test."):
                return True
        return self.returncode == 1 and not self.run_results.get("results")


class DbtLike(Protocol):
    def build(
        self,
        vars: dict[str, Any],
        target_path: Path,
        env: dict[str, str],
        *,
        exclude: list[str] | None = None,
        select: list[str] | None = None,
        full_refresh: bool = False,
    ) -> DbtResult: ...
    def freshness(self, vars: dict[str, Any], target_path: Path, env: dict[str, str]) -> DbtResult: ...
    def run_operation(
        self, macro: str, args: dict[str, Any], vars: dict[str, Any], target_path: Path, env: dict[str, str]
    ) -> DbtResult: ...


def repo_root() -> Path:
    return Path(os.environ.get("DX_REPO_ROOT") or Path(__file__).resolve().parents[2])


def dbt_executable() -> str:
    """File `dbt` trong cùng môi trường Python với tiến trình hiện tại."""
    import shutil

    bindir = Path(sys.executable).parent
    found = shutil.which("dbt", path=str(bindir)) or shutil.which("dbt")
    if not found:
        raise RuntimeError("Không tìm thấy dbt; chạy `uv sync`")
    return found


def default_target() -> str:
    return "local" if get_settings().is_local else "bigquery"


class DbtProject:
    def __init__(self, project_dir: Path | None = None, target: str | None = None) -> None:
        self.project_dir = project_dir or repo_root() / "transform"
        self.target = target or default_target()

    def _run(self, args: list[str], vars: dict[str, Any], target_path: Path, env: dict[str, str]) -> DbtResult:
        target_path.mkdir(parents=True, exist_ok=True)
        cmd = [
            dbt_executable(),
            *args,
            "--project-dir",
            str(self.project_dir),
            "--profiles-dir",
            str(self.project_dir),
            "--target",
            self.target,
            "--target-path",
            str(target_path),
            "--vars",
            json.dumps(vars, ensure_ascii=False),
        ]
        full_env = {**os.environ, **env, "DBT_SEND_ANONYMOUS_USAGE_STATS": "false", "PYTHONIOENCODING": "utf-8",
                    "PYTHONUTF8": "1"}
        proc = subprocess.run(
            cmd, cwd=self.project_dir, env=full_env, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        res = DbtResult(
            command=" ".join(args),
            returncode=proc.returncode,
            target_path=target_path,
            stdout_tail=(proc.stdout or "")[-6000:] + (proc.stderr or "")[-2000:],
        )
        rr = target_path / "run_results.json"
        if rr.exists():
            res.run_results = json.loads(rr.read_text(encoding="utf-8"))
        src = target_path / "sources.json"
        if src.exists():
            res.sources = json.loads(src.read_text(encoding="utf-8"))
        if proc.returncode not in (0, 1):
            log.warning("dbt %s thoát mã %s", args[0], proc.returncode)
        return res

    def build(
        self,
        vars: dict[str, Any],
        target_path: Path,
        env: dict[str, str],
        *,
        exclude: list[str] | None = None,
        select: list[str] | None = None,
        full_refresh: bool = False,
    ) -> DbtResult:
        args = ["build"]
        if select:
            args += ["--select", *select]
        if exclude:
            args += ["--exclude", *exclude]
        if full_refresh:
            args.append("--full-refresh")
        return self._run(args, vars, target_path, env)

    def freshness(self, vars: dict[str, Any], target_path: Path, env: dict[str, str]) -> DbtResult:
        return self._run(["source", "freshness", "--output", str(target_path / "sources.json")], vars, target_path, env)

    def run_operation(
        self, macro: str, args: dict[str, Any], vars: dict[str, Any], target_path: Path, env: dict[str, str]
    ) -> DbtResult:
        return self._run(["run-operation", macro, "--args", json.dumps(args)], vars, target_path, env)


def _test_name(uid: str) -> str:
    parts = uid.split(".")
    return parts[2] if len(parts) >= 3 else uid


def blocking_failures(build: DbtResult, freshness: DbtResult | None) -> list[dict[str, Any]]:
    """Test `severity: error` bị lỗi và nguồn quá hạn độ tươi (spec 02 §6.1, spec 04 §3.2)."""
    out: list[dict[str, Any]] = []
    for r in build.run_results.get("results", []):
        uid = r.get("unique_id", "")
        if uid.startswith("test.") and r.get("status") in ("fail", "error"):
            out.append(
                {
                    "test": _test_name(uid),
                    "unique_id": uid,
                    "severity": "error",
                    "failures": r.get("failures"),
                    "message": (r.get("message") or "")[:300],
                    "rows": [],
                }
            )
    if freshness:
        for r in freshness.sources.get("results", []):
            if r.get("status") in ("error", "runtime error"):
                uid = r.get("unique_id", "")
                out.append(
                    {
                        "test": "source_freshness",
                        "unique_id": uid,
                        "severity": "error",
                        "rows": [
                            {
                                "source": uid.split(".")[-2] if "." in uid else uid,
                                "table": uid.split(".")[-1],
                                "max_loaded_at": r.get("max_loaded_at"),
                                "age_hours": round(float(r.get("max_loaded_at_time_ago_in_s") or 0) / 3600, 1),
                            }
                        ],
                    }
                )
    return out


def warning_failures(build: DbtResult) -> list[str]:
    return [
        r["unique_id"]
        for r in build.run_results.get("results", [])
        if r.get("unique_id", "").startswith("test.") and r.get("status") == "warn"
    ]
