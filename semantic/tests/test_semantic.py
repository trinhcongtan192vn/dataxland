"""FR-MET-01, FR-MET-02, FR-MET-08 (spec 03 §11)."""

from __future__ import annotations

import copy
import filecmp
import shutil
import sys
from pathlib import Path

import pytest
import yaml

SEM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SEM))

import build  # noqa: E402
import check_versions  # noqa: E402


@pytest.fixture()
def lib_copy(tmp_path: Path) -> Path:
    dst = tmp_path / "semantic"
    shutil.copytree(SEM / "metrics", dst / "metrics")
    shutil.copy(SEM / "dimensions.yml", dst / "dimensions.yml")
    shutil.copy(SEM / "sources.yml", dst / "sources.yml")
    return dst


def _edit(root: Path, rel: str, fn: object) -> None:
    p = root / "metrics" / rel
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    fn(d)  # type: ignore[operator]
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")


@pytest.mark.parametrize(
    ("rel", "mutate", "message"),
    [
        ("seller/gmv.yml", lambda d: d.pop("name_vi"), "thiếu trường bắt buộc 'name_vi'"),
        (
            "seller/aov.yml",
            lambda d: d.update(numerator="khong_ton_tai"),
            "tham chiếu chỉ số không tồn tại 'khong_ton_tai'",
        ),
        (
            "seller/gmv.yml",
            lambda d: d.update(dimensions=[*d["dimensions"], "mau_sac"]),
            "chiều 'mau_sac' không có trong dimensions.yml",
        ),
        (
            "seller/gmv.yml",
            lambda d: d.update(dimensions=[*d["dimensions"], "campaign"]),
            "chiều 'campaign' không có trên mart nguồn",
        ),
        ("seller/gmv.yml", lambda d: d.update(version="1.1.0"), "version 1.1.0 không khớp phần tử cuối của history"),
    ],
)
def test_fr_met_01_build_rejects_invalid_yaml(lib_copy: Path, rel: str, mutate: object, message: str) -> None:
    _edit(lib_copy, rel, mutate)
    with pytest.raises(build.BuildError) as exc:
        build.run(lib_copy)
    assert message in str(exc.value)
    assert rel in str(exc.value)


def test_fr_met_01_rejects_cycle(lib_copy: Path) -> None:
    _edit(lib_copy, "seller/contribution_margin.yml", lambda d: d.update(formula="net_profit_after_fees - cogs"))
    with pytest.raises(build.BuildError, match="vòng lặp tham chiếu"):
        build.run(lib_copy)


def test_fr_met_02_generated_models_match(tmp_path: Path) -> None:
    """Chạy build hai lần cho kết quả giống hệt, và giống bản đã commit (CI: git diff --exit-code)."""
    a, b = tmp_path / "a", tmp_path / "b"
    build.run(SEM, a)
    build.run(SEM, b)
    for sub in ("cube/model", "dist"):
        cmp = filecmp.dircmp(a / sub, b / sub)
        assert not cmp.diff_files and not cmp.left_only and not cmp.right_only
        committed = filecmp.dircmp(a / sub, SEM / sub)
        assert not committed.diff_files, f"{sub} lệch YAML, chạy make semantic: {committed.diff_files}"


def test_every_metric_in_spec_present() -> None:
    lib = build.load(SEM)
    spec = {
        "ad_spend",
        "net_revenue_sales",
        "gross_sales",
        "roas_blended",
        "gmv",
        "net_revenue",
        "orders_placed",
        "order_count",
        "cancelled_orders",
        "returned_orders",
        "aov",
        "cancel_rate",
        "return_rate",
        "platform_fees",
        "payment_fees",
        "shipping_cost",
        "return_cost",
        "other_costs",
        "allocated_ad_spend",
        "cogs",
        "contribution_margin",
        "net_profit_after_fees",
        "net_margin_pct",
        "sku_profit",
        "impressions",
        "clicks",
        "conversions",
        "conversion_value",
        "ctr",
        "cpc",
        "cpm",
        "cpa",
        "roas_platform",
        "mer",
        "platform_vs_actual_gap",
        "amazon_ad_spend",
        "amazon_ad_sales",
        "amazon_total_sales",
        "acos",
        "tacos",
        "budget",
        "spend_mtd",
        "budget_used_pct",
        "budget_pacing",
    }
    assert spec <= set(lib.metrics), spec - set(lib.metrics)


def test_handbook_has_no_hidden_metrics() -> None:
    import json

    hb = json.loads((SEM / "dist" / "handbook.json").read_text(encoding="utf-8"))
    names = {m["metric"] for m in hb["metrics"]}
    assert "net_revenue" in names and "orders_placed" not in names
    nr = next(m for m in hb["metrics"] if m["metric"] == "net_profit_after_fees")
    assert nr["formula_vi"].startswith("Biên đóng góp −") or "Biên đóng góp" in nr["formula_vi"]
    assert nr["history"][-1]["version"] == nr["version"]


def test_fr_met_08_version_check() -> None:
    old = yaml.safe_load((SEM / "metrics" / "seller" / "aov.yml").read_text(encoding="utf-8"))
    new = copy.deepcopy(old)
    new["denominator"] = "orders_placed"
    errs = check_versions.compare(old, new, "aov.yml")
    assert any("không tăng version" in e for e in errs)
    new["version"] = "1.1.0"
    errs = check_versions.compare(old, new, "aov.yml")
    assert any("history" in e for e in errs)
    new["history"] = [*new["history"], {"version": "1.1.0", "date": "2026-10-20", "change_vi": "Đổi mẫu số"}]
    assert check_versions.compare(old, new, "aov.yml") == []
    down = copy.deepcopy(old)
    down["version"] = "0.9.0"
    down["history"] = [{"version": "0.9.0", "date": "2026-10-20", "change_vi": "x"}]
    assert any("giảm" in e for e in check_versions.compare(old, down, "aov.yml"))
    # Chỉ sửa mô tả: không bắt tăng version.
    desc = copy.deepcopy(old)
    desc["description_vi"] = "Mô tả mới"
    assert check_versions.compare(old, desc, "aov.yml") == []


def test_release_metrics_diff(tmp_path: Path) -> None:
    sys.path.insert(0, str(SEM.parent / "ops"))
    import release_metrics

    new = release_metrics.versions(SEM / "dist" / "metrics.json")
    old = dict(new, aov="0.9.0")
    old.pop("gmv")
    changes = release_metrics.diff(old, new)
    assert {"metric": "aov", "old_version": "0.9.0", "new_version": new["aov"]} in changes
    assert {"metric": "gmv", "old_version": None, "new_version": new["gmv"]} in changes
    assert len(changes) == 2
    # Lần đầu: chỉ ghi mốc.
    state = tmp_path / "state.json"
    assert release_metrics.main(["--state", str(state)]) == 0
    assert state.exists()
