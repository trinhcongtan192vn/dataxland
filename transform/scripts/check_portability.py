"""Quét SQL trong `models/core` và `models/marts`, báo lỗi khi gặp từ khóa riêng của BigQuery (NFR-07, spec 02 §7).

Chạy trong `make lint`. Trả mã 1 nếu có vi phạm.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = [
    ("SAFE_CAST", re.compile(r"\bsafe_cast\s*\(", re.I)),
    ("SAFE_DIVIDE", re.compile(r"\bsafe_divide\s*\(", re.I)),
    ("FORMAT_DATE", re.compile(r"\bformat_date\s*\(", re.I)),
    ("PARSE_DATE", re.compile(r"\bparse_date\s*\(", re.I)),
    ("PARSE_TIMESTAMP", re.compile(r"\bparse_timestamp\s*\(", re.I)),
    ("DATE_TRUNC dạng BigQuery", re.compile(r"\bdate_trunc\s*\(\s*[^,()]+,\s*(day|week|month|year|quarter)\s*\)", re.I)),
    ("ARRAY_AGG", re.compile(r"\barray_agg\s*\(", re.I)),
    ("STRUCT(", re.compile(r"\bstruct\s*\(", re.I)),
    ("UNNEST", re.compile(r"\bunnest\s*\(", re.I)),
    ("QUALIFY", re.compile(r"\bqualify\b", re.I)),
    ("backtick", re.compile(r"`")),
]
_JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.S)
_SQL_COMMENT = re.compile(r"--[^\n]*")


def scan(paths: list[Path]) -> list[str]:
    errors = []
    for p in paths:
        text = _SQL_COMMENT.sub("", _JINJA_COMMENT.sub("", p.read_text(encoding="utf-8")))
        for i, line in enumerate(text.splitlines(), 1):
            for name, rx in FORBIDDEN:
                if rx.search(line):
                    errors.append(f"{p.relative_to(ROOT)}:{i}: {name}")
    return errors


def main() -> int:
    files = sorted((ROOT / "models" / "core").rglob("*.sql")) + sorted((ROOT / "models" / "marts").rglob("*.sql"))
    errors = scan(files)
    for e in errors:
        print(e)
    print(f"check_portability: {len(files)} file, {len(errors)} vi phạm")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
