from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipelines"))
os.environ.setdefault("DX_ENV", "local")
os.environ.setdefault("DX_REPO_ROOT", str(REPO))
