"""Kiểm tra phiên bản chỉ số so với nhánh gốc (FR-MET-08, spec 03 §6). Chạy trong CI.

- Đổi trường tính toán (`measure`, `numerator`, `denominator`, `formula`, `source`, `variants`) mà không tăng
  `version` → lỗi.
- Tăng `version` mà phần tử cuối của `history` không khớp → lỗi.
- Giảm `version` → lỗi.

Cách dùng: `uv run python semantic/check_versions.py --base origin/main`
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
CALC_FIELDS = ("measure", "numerator", "denominator", "formula", "source", "variants")


def semver(v: str) -> tuple[int, int, int]:
    a, b, c = (int(x) for x in str(v).split("."))
    return a, b, c


def compare(old: dict[str, Any] | None, new: dict[str, Any], path: str) -> list[str]:
    errs: list[str] = []
    hist = new.get("history") or []
    if not hist or str(hist[-1].get("version")) != str(new.get("version")):
        errs.append(f"{path}: version {new.get('version')} không khớp phần tử cuối của history")
    if old is None:
        return errs
    ov, nv = semver(old["version"]), semver(new["version"])
    if nv < ov:
        errs.append(f"{path}: version giảm từ {old['version']} xuống {new['version']}")
    changed = [f for f in CALC_FIELDS if old.get(f) != new.get(f)]
    if changed and nv <= ov:
        errs.append(f"{path}: đổi {', '.join(changed)} mà không tăng version (đang {new['version']})")
    return errs


def base_file(base: str, rel: str) -> dict[str, Any] | None:
    proc = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{base}:{rel}"], capture_output=True, text=True, encoding="utf-8"
    )
    if proc.returncode != 0:
        return None
    data = yaml.safe_load(proc.stdout)
    return data if isinstance(data, dict) else None


def check(base: str) -> list[str]:
    errs: list[str] = []
    for p in sorted((ROOT / "metrics").rglob("*.yml")):
        rel = p.relative_to(REPO).as_posix()
        new = yaml.safe_load(p.read_text(encoding="utf-8"))
        errs += compare(base_file(base, rel), new, rel)
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main")
    args = ap.parse_args()
    errs = check(args.base)
    for e in errs:
        print(e)
    print(f"check_versions: {len(errs)} lỗi")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
