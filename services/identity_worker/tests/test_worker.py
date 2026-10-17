"""Ghép định danh (spec 10 §9): FR-ID-01, FR-ID-02, NFR-03."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "pipelines"))

from dx_pipelines.warehouse import DuckDBWarehouse  # noqa: E402
from identity_worker import judge as jd  # noqa: E402
from identity_worker import worker  # noqa: E402
from identity_worker.candidates import Product  # noqa: E402
from identity_worker.rules import Pair  # noqa: E402
from identity_worker.writer import product_map, surrogate  # noqa: E402

PREFIX = "t_demo_seller"


class FakeApi:
    """Giữ `identity_matches` trong bộ nhớ như API (khóa duy nhất theo cặp; giữ quyết định của người)."""

    def __init__(self) -> None:
        self.matches: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.suggest_runs = 0

    def post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        body = body or {}
        if path.endswith("/matches/keys"):
            return {"pair_keys": list(self.matches), "last_suggest_at": None}
        if path.endswith("/identity/matches"):
            for m in body["matches"]:
                self.matches.setdefault(m["pair_key"], dict(m))
            self.suggest_runs += int(bool(body.get("suggest_run")))
            return {}
        if path.endswith("/identity/approved"):
            return {
                "pairs": [
                    {
                        "left": f"{m['left']['source']}:{m['left']['source_id']}",
                        "right": f"{m['right']['source']}:{m['right']['source_id']}",
                        "method": m["method"],
                    }
                    for m in self.matches.values()
                    if m["status"] == "approved"
                ]
            }
        if path == "/v1/events":
            self.events.append(body)
            return {}
        raise AssertionError(path)

    def set_status(self, pred: Any, status: str) -> None:
        for m in self.matches.values():
            if pred(m):
                m["status"] = status


def _warehouse(tmp: Path) -> DuckDBWarehouse:
    wh = DuckDBWarehouse(tmp / "dx.duckdb")
    stg = f"{PREFIX}_stg"
    prod_cols = {
        "source_id": "string",
        "seller_sku": "string",
        "name": "string",
        "barcode": "string",
        "category_raw": "string",
    }
    wh.write_rows(
        stg,
        "stg_shopee__products",
        prod_cols,
        [
            {
                "source_id": "1000-50000",
                "seller_sku": "DS-SRM-C30",
                "name": "Serum Vitamin C 30ml chính hãng",
                "barcode": None,
                "category_raw": "Làm đẹp",
            },
            {
                "source_id": "1006-0",
                "seller_sku": "DS-CHONG-50",
                "name": "Kem chống nắng SPF50 50ml",
                "barcode": "8938500000066",
                "category_raw": "Làm đẹp",
            },
        ],
    )
    wh.write_rows(
        stg,
        "stg_tiktok_shop__products",
        prod_cols,
        [
            {
                "source_id": "17290000-170000",
                "seller_sku": "TT-SERUM-VITC",
                "name": "Tinh chất Serum Vitamin C 30ml",
                "barcode": None,
                "category_raw": "Serum",
            },
            {
                "source_id": "17290006-170006",
                "seller_sku": "TT-KCN-50",
                "name": "Kem chong nang SPF 50 50ml",
                "barcode": "8938500000066",
                "category_raw": "Làm đẹp",
            },
            {
                "source_id": "17290009-170009",
                "seller_sku": "TT-SON",
                "name": "Son môi đỏ cam 3g",
                "barcode": None,
                "category_raw": "Trang điểm",
            },
        ],
    )
    order_cols = {
        "source_id": "string",
        "buyer_ref": "string",
        "buyer_phone_hash": "string",
        "buyer_email_hash": "string",
        "ordered_at": "timestamp",
        "order_date": "date",
    }
    wh.write_rows(
        stg,
        "stg_shopee__orders",
        order_cols,
        [
            {
                "source_id": "S1",
                "buyer_ref": "900001",
                "buyer_phone_hash": "h-phone-1",
                "buyer_email_hash": None,
                "ordered_at": "2026-10-01 01:00:00",
                "order_date": "2026-10-01",
            },
        ],
    )
    wh.write_rows(
        stg,
        "stg_tiktok_shop__orders",
        order_cols,
        [
            {
                "source_id": "T1",
                "buyer_ref": "u1",
                "buyer_phone_hash": "h-phone-1",
                "buyer_email_hash": "h-mail-1",
                "ordered_at": "2026-10-05 01:00:00",
                "order_date": "2026-10-05",
            },
            {
                "source_id": "T2",
                "buyer_ref": "u2",
                "buyer_phone_hash": "h-phone-2",
                "buyer_email_hash": None,
                "ordered_at": "2026-10-06 01:00:00",
                "order_date": "2026-10-06",
            },
        ],
    )
    line_cols = {"order_source_id": "string", "seller_sku": "string", "unit_price_vnd": "numeric"}
    wh.write_rows(
        stg,
        "stg_shopee__order_lines",
        line_cols,
        [{"order_source_id": "S1", "seller_sku": "DS-SRM-C30", "unit_price_vnd": 269000}],
    )
    wh.write_rows(
        stg,
        "stg_tiktok_shop__order_lines",
        line_cols,
        [{"order_source_id": "T1", "seller_sku": "TT-SERUM-VITC", "unit_price_vnd": 259000}],
    )
    return wh


def _judge_same(system: str, messages: list[dict[str, Any]]) -> str:
    items = json.loads(messages[0]["content"])
    return json.dumps(
        {
            "results": [
                {
                    "pair": it["pair"],
                    "same": "vitamin" in it["a"]["name"].lower(),
                    "confidence": 0.95,
                    "reason_vi": "Cùng serum Vitamin C 30ml",
                }
                for it in items
            ]
        }
    )


def _run(wh: DuckDBWarehouse, api: FakeApi, call: Any = _judge_same) -> worker.RunStats:
    return worker.run("demo_seller", PREFIX, ["shopee", "tiktok_shop"], 0.7, wh, api, "2026-10-16", call, "r1")


def _map(wh: DuckDBWarehouse) -> dict[str, str]:
    rows = wh.query(f'select entity, source, source_id, canonical_id from "{PREFIX}_core"."identity_map"')
    return {f"{e}|{s}:{i}": c for e, s, i, c in rows}


def test_fr_id_01_rule_barcode_auto_approved(tmp_path: Path) -> None:
    wh, api = _warehouse(tmp_path), FakeApi()
    _run(wh, api)
    rule = [m for m in api.matches.values() if m["method"] == "rule_barcode"]
    assert len(rule) == 1 and rule[0]["status"] == "approved"
    m = _map(wh)
    assert m["product|shopee:1006-0"] == m["product|tiktok_shop:17290006-170006"]


def test_fr_id_01_suggestion_needs_review(tmp_path: Path) -> None:
    wh, api = _warehouse(tmp_path), FakeApi()
    st = _run(wh, api)
    sugg = [m for m in api.matches.values() if m["status"] == "proposed"]
    assert st.suggestions == len(sugg) == 1
    assert {sugg[0]["left"]["source_id"], sugg[0]["right"]["source_id"]} == {"1000-50000", "17290000-170000"}
    assert sugg[0]["reason_vi"] and sugg[0]["score"] >= 0.7
    assert "product|shopee:1000-50000" not in _map(wh)  # chưa duyệt thì chưa vào identity_map
    api.set_status(lambda m: m["status"] == "proposed", "approved")
    _run(wh, api)
    m = _map(wh)
    assert m["product|shopee:1000-50000"] == m["product|tiktok_shop:17290000-170000"]
    # Chưa có doanh thu 90 ngày (không có marts): canonical là khóa SKU của một trong hai thành viên.
    assert m["product|shopee:1000-50000"] in {surrogate("ds-srm-c30"), surrogate("tt-serum-vitc")}


def test_fr_id_01_undo_splits_group_and_canonical_stable(tmp_path: Path) -> None:
    products = [
        Product("shopee", "a", "A", "x", None, None, revenue_90d=10),
        Product("tiktok_shop", "b", "B", "x", None, None, revenue_90d=5),
        Product("lazada", "c", "C", "x", None, None, revenue_90d=100),
    ]
    pairs = [Pair("product", "shopee:a", "tiktok_shop:b", "llm"), Pair("product", "tiktok_shop:b", "lazada:c", "llm")]
    first = product_map(products, pairs, {})
    assert len(set(first.values())) == 1 and first["shopee:a"] == surrogate("c")
    # Gỡ cặp b–c: nhóm {a, b} giữ canonical cũ? Nhóm lớn hơn giữ; hai nhóm bằng nhau → nhóm có c (đã gỡ) tách ra.
    after = product_map(products, pairs[:1], first)
    assert after["shopee:a"] == after["tiktok_shop:b"] == first["shopee:a"]
    assert "lazada:c" not in after
    # Chạy lại không đổi canonical_id.
    assert product_map(products, pairs, first) == first


def test_fr_id_02_customer_merge_by_phone_and_email(tmp_path: Path) -> None:
    wh, api = _warehouse(tmp_path), FakeApi()
    _run(wh, api)
    m = _map(wh)
    # S1 (Shopee) và T1 (TikTok) cùng phone_hash → cùng người; canonical là khóa của đơn sớm nhất (S1).
    assert m["customer|shopee:S1"] == m["customer|tiktok_shop:T1"] == surrogate("shopee", "900001")
    assert "customer|tiktok_shop:T2" not in m


def test_canonical_id_stable_and_change_event(tmp_path: Path) -> None:
    wh, api = _warehouse(tmp_path), FakeApi()
    st1 = _run(wh, api)
    first = _map(wh)
    st2 = _run(wh, api)
    assert _map(wh) == first
    assert st1.changed and not st2.changed
    assert len(api.events) == 1 and api.events[0]["type"] == "identity.changed"


def test_nfr_03_judge_payload_has_no_buyer_data(tmp_path: Path) -> None:
    sent: list[Any] = []

    def spy(system: str, messages: list[dict[str, Any]]) -> str:
        sent.append(messages)
        return _judge_same(system, messages)

    wh, api = _warehouse(tmp_path), FakeApi()
    _run(wh, api, spy)
    assert sent
    for msgs in sent:
        for item in json.loads(msgs[0]["content"]):
            for side in ("a", "b"):
                assert set(item[side]) <= jd.ALLOWED_FIELDS
        text = json.dumps(msgs, ensure_ascii=False)
        assert "h-phone" not in text and "900001" not in text and "buyer" not in text


def test_without_api_key_still_needs_review(tmp_path: Path) -> None:
    wh, api = _warehouse(tmp_path), FakeApi()
    st = _run(wh, api, None)
    assert st.judged == 0 and any("Anthropic" in n for n in st.notes)
    assert all(m["status"] in ("approved", "proposed") for m in api.matches.values())
    assert all(m["method"].startswith("rule") for m in api.matches.values() if m["status"] == "approved")


@pytest.mark.parametrize(("a", "b", "exp"), [("8938500000066", " 8938500000066 ", True), ("123", "123", False)])
def test_barcode_rule_normalization(a: str, b: str, exp: bool) -> None:
    from identity_worker.rules import product_rules

    ps = [Product("shopee", "1", None, "x", a, None), Product("tiktok_shop", "2", None, "y", b, None)]
    assert bool(product_rules(ps)) is exp
