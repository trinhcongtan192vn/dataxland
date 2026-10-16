"""In OpenAPI của API ra stdout (dùng cho `pnpm --filter web gen:api`, spec 05 §10)."""

from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("DX_ENV", "local")

from app.main import create_app

json.dump(create_app().openapi(), sys.stdout, ensure_ascii=False, indent=1, sort_keys=True)
