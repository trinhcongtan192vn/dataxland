"""Bộ đánh giá hỏi đáp (spec 09 §7, FR-AI-03): gọi `ask()` thật trên stack local với dữ liệu mẫu.

    uv run python ai/run_evals.py seller agency [--out .local/evals]

Ngưỡng qua: ≥ 90% câu đạt; 100% câu `refuse` đạt; 100% câu trả lời có chân trang đúng. Thoát mã 1 khi không đạt.
Cần `ANTHROPIC_API_KEY`, Postgres (`DATABASE_URL`) và Cube đang chạy. Không ghi gì vào Postgres (rollback cuối lượt).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent
PASS_RATE = 0.9


@dataclass
class CaseResult:
    id: str
    ok: bool
    kind: str
    reasons: list[str] = field(default_factory=list)
    answer: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)


def load_cases(pack: str) -> list[dict[str, Any]]:
    data = yaml.safe_load((ROOT / "evals" / f"{pack}.yaml").read_text(encoding="utf-8"))
    return list(data or [])


def kind_of(expect: dict[str, Any]) -> str:
    for k in ("refuse", "missing_metric", "no_numbers", "no_other_tenant"):
        if expect.get(k):
            return k
    return "answer"


def footer_ok(citations: list[dict[str, Any]]) -> bool:
    return bool(citations) and all(
        c.get("name_vi") and c.get("version") and (c.get("time") or {}).get("from") and "data_as_of" in c
        for c in citations
    )


def numeric_ok(answer: str, value: float | None, unit: str, tolerance_pct: float) -> bool:
    from app.ask.guard import answer_numbers

    if value is None:
        return True
    targets = [value, value * 100] if unit == "percent" else [value]
    for got, tol, _ in answer_numbers(answer):
        for t in targets:
            if abs(abs(got) - abs(t)) <= max(tol, abs(t) * tolerance_pct / 100):
                return True
    return False


def evaluate(case: dict[str, Any], res: Any, direct: Any) -> CaseResult:
    from app.ask.guard import answer_numbers
    from app.metrics.periods import resolve

    exp = case.get("expect") or {}
    kind = kind_of(exp)
    out = CaseResult(case["id"], True, kind, answer=res.answer_vi, citations=res.citations)

    def fail(msg: str) -> None:
        out.ok = False
        out.reasons.append(msg)

    if kind == "refuse":
        if not res.refused_reason or res.refused_reason in ("answer_failed", "model_unavailable"):
            fail("không từ chối")
        return out
    if res.refused_reason:
        fail(f"bị từ chối: {res.refused_reason}")
    if kind == "missing_metric":
        if not res.missing_metric:
            fail("không ghi nhận chỉ số còn thiếu")
        return out
    if kind == "no_numbers":
        if res.citations or answer_numbers(res.answer_vi):
            fail("câu ngoài chủ đề vẫn có số")
        return out
    if kind == "no_other_tenant":
        other = case.get("other_tenant_name")
        if other and other in res.answer_vi:
            fail("nhắc tới khách khác")
        return out
    if not footer_ok(res.citations):
        fail("chân trang thiếu chỉ số, phiên bản, kỳ hoặc thời điểm dữ liệu")
    cited = {c["metric"] for c in res.citations}
    for m in exp.get("metrics") or []:
        if m not in cited:
            fail(f"không truy vấn {m}")
    preset = (exp.get("time") or {}).get("preset")
    if preset:
        p = resolve({"preset": preset})
        want = {"from": p.start.isoformat(), "to": p.end.isoformat()}
        if not any(c.get("time") == want for c in res.citations if c["metric"] in set(exp.get("metrics") or [])):
            fail(f"kỳ không đúng {preset}")
    num = exp.get("numeric")
    if num and direct is not None:
        value, unit = direct
        if not numeric_ok(res.answer_vi, value, unit, float(num.get("tolerance_pct", 0.5))):
            fail(f"số {num['metric']} không khớp API ({value})")
    return out


def run_pack(pack: str, db: Any) -> dict[str, Any]:
    from app.ask.engine import ask
    from app.auth.context import internal_ctx
    from app.metrics.engine import QueryIn, query

    names = {"demo_seller": "Shop Demo", "demo_agency": "Brand Demo"}
    results: list[CaseResult] = []
    for case in load_cases(pack):
        ctx = internal_ctx(db, case["tenant"])
        ctx.role, ctx.caller = "owner", "user"
        exp = case.get("expect") or {}
        direct = None
        if num := exp.get("numeric"):
            preset = (exp.get("time") or {}).get("preset")
            r = query(ctx, QueryIn(metrics=[num["metric"]], time={"preset": preset} if preset else None), db=db)
            rows = r["rows"]
            direct = (rows[0].get(num["metric"]) if rows else None, r["metrics"][num["metric"]]["unit"])
        other = next(t for t in names if t != case["tenant"])
        case.setdefault("other_tenant_name", names[other])
        sp = db.begin_nested()
        res = ask(db, ctx, case["question"], "eval")
        sp.rollback()
        cr = evaluate(case, res, direct)
        results.append(cr)
        mark = "OK " if cr.ok else "LỖI"
        print(f"[{mark}] {cr.id}: {'; '.join(cr.reasons)}")
    total = len(results)
    passed = sum(r.ok for r in results)
    refuse = [r for r in results if r.kind == "refuse"]
    answered = [r for r in results if r.kind == "answer"]
    report = {
        "pack": pack,
        "total": total,
        "passed": passed,
        "pass_rate": passed / total if total else 0,
        "refuse_rate": sum(r.ok for r in refuse) / len(refuse) if refuse else 1,
        "footer_rate": sum(footer_ok(r.citations) for r in answered) / len(answered) if answered else 1,
        "cases": [r.__dict__ for r in results],
    }
    report["ok"] = report["pass_rate"] >= PASS_RATE and report["refuse_rate"] == 1 and report["footer_rate"] == 1
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("packs", nargs="*", default=["seller", "agency"])
    ap.add_argument("--out", default=".local/evals")
    args = ap.parse_args(argv)

    from dx_common.config import get_settings
    from dx_common.db import session_factory

    if not get_settings().anthropic_api_key:
        print("Thiếu ANTHROPIC_API_KEY", file=sys.stderr)
        return 2
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = True
    for pack in args.packs:
        db = session_factory()()
        try:
            rep = run_pack(pack, db)
        finally:
            db.rollback()
            db.close()
        (out_dir / f"{pack}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2, default=str), "utf-8")
        print(
            f"{pack}: {rep['passed']}/{rep['total']} đạt ({rep['pass_rate']:.0%}), từ chối {rep['refuse_rate']:.0%}, "
            f"chân trang {rep['footer_rate']:.0%} → {'ĐẠT' if rep['ok'] else 'KHÔNG ĐẠT'}"
        )
        ok = ok and rep["ok"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
