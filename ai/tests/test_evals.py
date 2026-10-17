"""Bộ đánh giá AI (spec 09 §7, FR-AI-03).

Kiểm tra cấu trúc bộ câu luôn chạy. Lượt đánh giá thật gọi model nên chỉ chạy khi `DX_RUN_EVALS=1` và có
`ANTHROPIC_API_KEY` (CI chạy khi đổi `semantic/`, `ai/`, `knowledge/playbooks/`, `services/api/app/ask/`).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DX_REPO_ROOT", str(REPO))

import run_evals  # noqa: E402

PRESETS = {
    "today",
    "yesterday",
    "this_week",
    "last_week",
    "this_month",
    "last_month",
    "last_7_days",
    "last_30_days",
    "last_90_days",
}


@pytest.mark.parametrize("pack", ["seller", "agency"])
def test_eval_sets_well_formed(pack: str) -> None:
    metrics = json.loads((REPO / "semantic" / "dist" / "metrics.json").read_text(encoding="utf-8"))["metrics"]
    cases = run_evals.load_cases(pack)
    assert len(cases) >= 40
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    kinds = {run_evals.kind_of(c.get("expect") or {}) for c in cases}
    assert {"answer", "refuse", "missing_metric"} <= kinds
    for c in cases:
        assert c["tenant"] == f"demo_{pack}" and c["question"].strip()
        exp = c.get("expect") or {}
        for m in exp.get("metrics") or []:
            assert m in metrics and pack in metrics[m]["packs"], (c["id"], m)
        if t := exp.get("time"):
            assert t["preset"] in PRESETS
        if n := exp.get("numeric"):
            assert n["metric"] in (exp.get("metrics") or [])


def _res(answer: str, citations: list[dict[str, object]] | None = None, **kw: object) -> SimpleNamespace:
    return SimpleNamespace(
        answer_vi=answer, citations=citations or [], refused_reason=kw.get("refused"), missing_metric=kw.get("missing")
    )


def test_evaluate_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DX_TODAY", "2026-10-16")
    cite = {
        "metric": "net_revenue",
        "name_vi": "Doanh thu thực nhận",
        "version": "1.0.0",
        "time": {"from": "2026-10-05", "to": "2026-10-11"},
        "data_as_of": "2026-10-16T00:00:00Z",
    }
    case = {
        "id": "x",
        "expect": {
            "metrics": ["net_revenue"],
            "time": {"preset": "last_week"},
            "numeric": {"metric": "net_revenue", "tolerance_pct": 0.5},
        },
    }
    assert run_evals.evaluate(case, _res("Doanh thu 10.000.000 ₫", [cite]), (10_000_000, "VND")).ok
    bad = run_evals.evaluate(case, _res("Doanh thu 12.000.000 ₫", [cite]), (10_000_000, "VND"))
    assert not bad.ok and "không khớp" in bad.reasons[0]
    nofoot = run_evals.evaluate(case, _res("Doanh thu 10.000.000 ₫"), (10_000_000, "VND"))
    assert not nofoot.ok
    refuse = {"id": "r", "expect": {"refuse": True}}
    assert run_evals.evaluate(refuse, _res("x", refused="buyer_pii"), None).ok
    assert not run_evals.evaluate(refuse, _res("x"), None).ok
    pct = {"id": "p", "expect": {"metrics": ["net_revenue"], "numeric": {"metric": "net_revenue", "tolerance_pct": 1}}}
    assert run_evals.numeric_ok("Tỷ lệ hoàn 4,2%", 0.0421, "percent", 1)
    assert run_evals.evaluate(pct, _res("10 triệu", [cite]), (10_000_000, "VND")).ok


@pytest.mark.skipif(
    not (os.environ.get("DX_RUN_EVALS") == "1" and os.environ.get("ANTHROPIC_API_KEY")),
    reason="chỉ chạy với DX_RUN_EVALS=1 và ANTHROPIC_API_KEY trên stack local",
)
def test_fr_ai_03_evals_pass(tmp_path: Path) -> None:
    assert run_evals.main(["seller", "agency", "--out", str(tmp_path)]) == 0
