"""`python -m dx_common.tenants validate tenants/` (spec 04 §1.1, chạy trong CI)."""

from __future__ import annotations

import sys

from dx_common.tenants.validate import validate_dir


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "validate":
        print("Cách dùng: python -m dx_common.tenants validate <thư mục>")
        return 2
    ok, errs = validate_dir(argv[1])
    for tid in sorted(ok):
        print(f"OK   {tid}")
    for e in errs:
        print(f"LỖI  {e.path}")
        for msg in e.errors:
            print(f"     - {msg}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
