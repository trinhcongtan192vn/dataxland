"""Chạy ghép định danh cho một khách (spec 10 §1–§6).

1. Ứng viên từ `stg`.
2. Quy tắc (tự duyệt) cho sản phẩm và người mua.
3. Gợi ý sản phẩm: chặn khối → điểm độ giống → Claude so cặp (khi có khóa API) → cặp đạt ngưỡng vào hàng chờ.
4. Gửi cặp sản phẩm cho API (Postgres `identity_matches`), lấy lại mọi cặp đã duyệt.
5. Ghi `t_<id>_core.identity_map`; nếu bản đồ đổi thì phát `identity.changed` để chạy lại dbt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from identity_worker import candidates as cand
from identity_worker import judge as jd
from identity_worker import rules, similarity, writer
from identity_worker.rules import Pair

SIM_FOR_JUDGE = 0.5


class Api(Protocol):
    def post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]: ...


@dataclass
class RunStats:
    product_rule_pairs: int = 0
    customer_rule_pairs: int = 0
    suggestions: int = 0
    judged: int = 0
    map_rows: int = 0
    changed: bool = False
    notes: list[str] = field(default_factory=list)


def score(sim: float, verdict: jd.Verdict | None) -> tuple[float, str | None]:
    """`score = 0,4 × sim + 0,6 × confidence`; model nói khác thì tối đa 0,3 (spec 10 §4 bước 4)."""
    if verdict is None:
        return sim, None
    s = 0.4 * sim + 0.6 * verdict.confidence
    if not verdict.same:
        s = min(s, 0.3)
    return round(s, 4), verdict.reason_vi


def _label(p: cand.Product) -> dict[str, Any]:
    return {
        "source": p.source,
        "source_id": p.source_id,
        "label": f"{p.name or ''} ({p.seller_sku or '—'})",
        "name": p.name,
        "seller_sku": p.seller_sku,
        "price_vnd": round(p.price) if p.price else None,
        "category": p.category,
    }


def run(
    tenant_id: str,
    prefix: str,
    sources: list[str],
    threshold: float,
    wh: cand.Warehouse,
    api: Api,
    today: str,
    call: jd.Caller | None = None,
    run_id: str | None = None,
    *,
    suggest: bool | None = True,
    publish_change: bool = True,
) -> RunStats:
    """`suggest = False`: chỉ ghép theo quy tắc và ghi lại bản đồ (sau quyết định duyệt); gợi ý tối đa một lần/ngày."""
    st = RunStats()
    c = cand.load(wh, prefix, [s for s in sources if s in cand.SALES], today)
    prod_rules = rules.product_rules(c.products)
    cust_rules = rules.customer_rules(c.orders)
    st.product_rule_pairs, st.customer_rule_pairs = len(prod_rules), len(cust_rules)
    by_key = {p.key: p for p in c.products}

    info = api.post("/v1/internal/identity/matches/keys", {"tenant_id": tenant_id})
    existing = info.get("pair_keys", [])
    if suggest is None:  # mặc định: gợi ý khi lần gợi ý gần nhất đã quá 24 giờ
        from datetime import datetime, timedelta

        from dx_common.timeutil import now_utc as _now

        last = info.get("last_suggest_at")
        suggest = not last or _now() - datetime.fromisoformat(str(last)) > timedelta(hours=24)
    rule_keys = {p.key for p in prod_rules}
    suggestions: list[dict[str, Any]] = []
    pairs = similarity.candidate_pairs(c.products, exclude=set(existing) | rule_keys) if suggest else []
    to_judge = [(a, b) for a, b, s in pairs if s >= SIM_FOR_JUDGE]
    verdicts: list[jd.Verdict | None] = jd.judge(to_judge, call) if (call and to_judge) else [None] * len(to_judge)
    if not call and to_judge:
        st.notes.append("không có khóa Anthropic: điểm gợi ý chỉ dựa trên độ giống, vẫn phải duyệt")
    st.judged = len(to_judge) if call else 0
    sims = {(a.key, b.key): s for a, b, s in pairs}
    for (a, b), v in zip(to_judge, verdicts, strict=True):
        sc, reason = score(sims[(a.key, b.key)], v)
        if sc >= threshold:
            suggestions.append(
                {
                    "entity": "product",
                    "left": _label(a),
                    "right": _label(b),
                    "pair_key": Pair("product", a.key, b.key, "").key,
                    "method": "llm" if v else "similarity",
                    "score": sc,
                    "reason_vi": reason,
                    "status": "proposed",
                }
            )
    st.suggestions = len(suggestions)
    auto = [
        {
            "entity": "product",
            "left": _label(by_key[p.left]),
            "right": _label(by_key[p.right]),
            "pair_key": p.key,
            "method": p.method,
            "score": 1.0,
            "reason_vi": None,
            "status": "approved",
        }
        for p in prod_rules
    ]
    api.post(
        "/v1/internal/identity/matches",
        {"tenant_id": tenant_id, "run_id": run_id, "suggest_run": suggest, "matches": auto + suggestions},
    )

    approved_raw = api.post("/v1/internal/identity/approved", {"tenant_id": tenant_id}).get("pairs", [])
    approved = [Pair("product", a["left"], a["right"], a["method"]) for a in approved_raw]
    prev = _previous_map(wh, prefix)
    pmap = writer.product_map(c.products, approved, prev.get("product", {}))
    cmap = writer.customer_map(c.orders, cust_rules, prev.get("customer", {}))
    pmethods = {m: p.method for p in approved for m in (p.left, p.right)}
    cmethods = {m: p.method for p in cust_rules for m in (p.left, p.right)}
    from dx_common.timeutil import now_utc

    now = now_utc()
    new_rows = writer.rows("product", pmap, pmethods, now) + writer.rows("customer", cmap, cmethods, now)
    st.changed = {
        k: v for e, m in (("product", pmap), ("customer", cmap)) for k, v in ((f"{e}|{a}", b) for a, b in m.items())
    } != {k: v for e, m in prev.items() for k, v in ((f"{e}|{a}", b) for a, b in m.items())}
    wh.write_rows(f"{prefix}_core", "identity_map", writer.COLUMNS, new_rows)
    st.map_rows = len(new_rows)
    if st.changed and publish_change:
        api.post("/v1/events", {"type": "identity.changed", "tenant_id": tenant_id, "payload": {"entity": "all"}})
    return st


def _previous_map(wh: cand.Warehouse, prefix: str) -> dict[str, dict[str, str]]:
    core = f"{prefix}_core"
    if "identity_map" not in set(wh.list_tables(core)):
        return {}
    q = '"' if wh.kind == "duckdb" else "`"
    out: dict[str, dict[str, str]] = {}
    for entity, source, source_id, canon in wh.query(
        f"select entity, source, source_id, canonical_id from {q}{core}{q}.{q}identity_map{q}"
    ):
        out.setdefault(str(entity), {})[f"{source}:{source_id}"] = str(canon)
    return out
