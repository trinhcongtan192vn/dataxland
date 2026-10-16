"""In OpenAPI của API ra stdout (dùng cho `pnpm --filter web gen:api`, spec 05 §10)."""

from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("DX_ENV", "local")

from app.main import create_app

# Ghi bytes để không bị đổi xuống dòng thành CRLF trên Windows.
body = json.dumps(create_app().openapi(), ensure_ascii=False, indent=1, sort_keys=True)
sys.stdout.buffer.write(body.encode("utf-8") + b"\n")
