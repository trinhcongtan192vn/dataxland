"""Phát `metric.released` cho mỗi chỉ số đổi phiên bản sau khi triển khai (spec 03 §6, spec 04 §4).

So `semantic/dist/metrics.json` vừa triển khai với ảnh chụp phiên bản lần phát hành trước (`--state`, mặc định
`.local/metrics_released.json`), rồi ghi ảnh chụp mới. Lần chạy đầu (chưa có ảnh chụp) chỉ ghi mốc, không phát sự
kiện, để khách không nhận thông báo "đổi định nghĩa" cho cả thư viện.

Cách dùng: `uv run python ops/release_metrics.py [--dry-run]`
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def versions(metrics_json: Path) -> dict[str, str]:
    data = json.loads(metrics_json.read_text(encoding="utf-8"))
    return {name: str(m["version"]) for name, m in data["metrics"].items()}


def diff(old: dict[str, str], new: dict[str, str]) -> list[dict[str, str | None]]:
    return [
        {"metric": k, "old_version": old.get(k), "new_version": v} for k, v in sorted(new.items()) if old.get(k) != v
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", type=Path, default=REPO / "semantic" / "dist" / "metrics.json")
    ap.add_argument("--state", type=Path, default=REPO / ".local" / "metrics_released.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    new = versions(args.metrics)
    if not args.state.exists():
        print(f"release_metrics: chưa có ảnh chụp, ghi mốc {len(new)} chỉ số, không phát sự kiện")
        changes: list[dict[str, str | None]] = []
    else:
        changes = diff(json.loads(args.state.read_text(encoding="utf-8")), new)
        for c in changes:
            print(f"{c['metric']}: {c['old_version']} → {c['new_version']}")
    if args.dry_run:
        return 0
    if changes:
        from dx_common.db import session_scope
        from dx_common.events import publish

        with session_scope() as db:
            for c in changes:
                publish("metric.released", None, c, "ops-release", bind=db)
    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.state.write_text(json.dumps(new, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"release_metrics: phát {len(changes)} sự kiện metric.released")
    return 0


if __name__ == "__main__":
    sys.exit(main())
