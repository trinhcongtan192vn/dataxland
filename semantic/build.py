"""Sinh model Cube, sổ tay chỉ số và ngữ cảnh AI từ thư viện chỉ số YAML (FR-MET-01, FR-MET-02, spec 03 §9).

Đầu vào: `metrics/**/*.yml`, `dimensions.yml`, `sources.yml`. Đầu ra (không sửa tay):

| File | Nội dung |
|---|---|
| `cube/model/<mart>.yml` | Một cube cho mỗi mart: measure cho chỉ số tính được trong mart đó, dimension, pre-aggregation |
| `dist/metrics.json` | Registry cho `services/api` |
| `dist/handbook.json` | Sổ tay cho cổng |
| `dist/ai_context.md` | Bảng chỉ số và từ đồng nghĩa cho AI |

Từ chối (thoát mã 1, nêu file và trường) khi: thiếu trường bắt buộc, tham chiếu chỉ số không tồn tại, vòng lặp tham
chiếu, chiều không có trong `dimensions.yml`, chiều không có trên mart nguồn, `version` không khớp phần tử cuối của
`history`. Đầu ra ổn định (sắp xếp khóa) để `git diff --exit-code` trong CI có nghĩa.

Mở rộng ghi ở ADR 0002 #19: chỉ số `simple` có thể khai báo `variants` – cùng định nghĩa tính trên mart khác (ví dụ
`net_revenue` trên mart dòng đơn khi cần chiều sản phẩm). Chỉ số `ratio`/`derived` tự có mặt ở mọi mart mà mọi
thành phần đều tính được.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent

REQUIRED = [
    "metric",
    "name_vi",
    "description_vi",
    "version",
    "type",
    "dimensions",
    "time_grains",
    "unit",
    "good_direction",
    "packs",
    "source_note_vi",
    "owner",
    "history",
]
OPTIONAL = {
    "source",
    "measure",
    "numerator",
    "denominator",
    "formula",
    "hidden",
    "requires",
    "anomaly",
    "synonyms_vi",
    "variants",
    "required_dimensions",
}
TYPES = {"simple", "ratio", "derived"}
UNITS = {"VND", "ratio", "percent", "count"}
DIRECTIONS = {"up", "down", "none"}
GRAINS = {"day", "week", "month"}
PACKS = {"seller", "agency"}
REQUIRES = {"identity", "amazon"}
AGGS = {"sum": "sum", "count": "count", "count_distinct": "count_distinct", "avg": "avg", "min": "min", "max": "max"}
ADDITIVE = {"sum", "count"}
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
TOKEN = re.compile(r"\s*(?:(\d+(?:\.\d+)?)|([a-z_][a-z0-9_]*)|([-+*/()]))")

STATUS_CUBE = "mrt_common__data_status"


class BuildError(Exception):
    pass


@dataclass
class Library:
    metrics: dict[str, dict[str, Any]]
    files: dict[str, str]
    dimensions: dict[str, dict[str, Any]]
    sources: dict[str, dict[str, Any]]
    errors: list[str] = field(default_factory=list)


def tokens(formula: str) -> list[str]:
    out: list[str] = []
    pos = 0
    while pos < len(formula):
        if formula[pos:].strip() == "":
            break
        mt = TOKEN.match(formula, pos)
        if not mt:
            raise BuildError(f"ký tự không hợp lệ trong formula ở vị trí {pos}: {formula[pos : pos + 10]!r}")
        out.append(next(g for g in mt.groups() if g is not None))
        pos = mt.end()
    return out


def refs(m: dict[str, Any]) -> list[str]:
    if m["type"] == "ratio":
        return [m["numerator"], m["denominator"]]
    if m["type"] == "derived":
        return [t for t in tokens(m["formula"]) if re.match(r"^[a-z_]", t)]
    return []


def load(root: Path = ROOT) -> Library:
    dims = yaml.safe_load((root / "dimensions.yml").read_text(encoding="utf-8")) or {}
    sources = yaml.safe_load((root / "sources.yml").read_text(encoding="utf-8")) or {}
    metrics: dict[str, dict[str, Any]] = {}
    files: dict[str, str] = {}
    lib = Library(metrics, files, dims, sources)
    for p in sorted((root / "metrics").rglob("*.yml")):
        rel = p.relative_to(root).as_posix()
        try:
            d = yaml.safe_load(p.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            lib.errors.append(f"{rel}: YAML lỗi: {exc}")
            continue
        if not isinstance(d, dict):
            lib.errors.append(f"{rel}: file phải là object YAML")
            continue
        name = d.get("metric")
        if name and name != p.stem:
            lib.errors.append(f"{rel}: metric '{name}' không trùng tên file")
        if name in metrics:
            lib.errors.append(f"{rel}: metric '{name}' trùng với {files[name]}")
        if name:
            metrics[name] = d
            files[name] = rel
    return lib


def validate(lib: Library) -> None:
    e = lib.errors
    for name, m in lib.metrics.items():
        f = lib.files[name]
        for k in REQUIRED:
            if k not in m or m[k] in (None, "", []):
                e.append(f"{f}: thiếu trường bắt buộc '{k}'")
        unknown = set(m) - set(REQUIRED) - OPTIONAL
        if unknown:
            e.append(f"{f}: trường không hỗ trợ: {', '.join(sorted(unknown))}")
        t = m.get("type")
        if t not in TYPES:
            e.append(f"{f}: type phải là simple, ratio hoặc derived")
            continue
        if not SEMVER.match(str(m.get("version", ""))):
            e.append(f"{f}: version phải theo semver")
        hist = m.get("history") or []
        if not hist or str(hist[-1].get("version")) != str(m.get("version")):
            e.append(f"{f}: version {m.get('version')} không khớp phần tử cuối của history")
        for h in hist:
            if not {"version", "date", "change_vi"} <= set(h):
                e.append(f"{f}: mỗi phần tử history cần version, date, change_vi")
        if m.get("unit") not in UNITS:
            e.append(f"{f}: unit không hợp lệ")
        if m.get("good_direction") not in DIRECTIONS:
            e.append(f"{f}: good_direction không hợp lệ")
        if not set(m.get("time_grains") or []) <= GRAINS:
            e.append(f"{f}: time_grains chỉ gồm day, week, month")
        if not set(m.get("packs") or []) <= PACKS:
            e.append(f"{f}: packs chỉ gồm seller, agency")
        if not set(m.get("requires") or []) <= REQUIRES:
            e.append(f"{f}: requires chỉ gồm identity, amazon")
        for dname in m.get("dimensions") or []:
            if dname not in lib.dimensions:
                e.append(f"{f}: chiều '{dname}' không có trong dimensions.yml")
        if t == "simple":
            for part in [{"source": m.get("source"), "measure": m.get("measure")}, *(m.get("variants") or [])]:
                src, ms = part.get("source"), part.get("measure")
                if src not in lib.sources:
                    e.append(f"{f}: source '{src}' không có trong sources.yml")
                if not isinstance(ms, dict) or ms.get("agg") not in AGGS or not ms.get("column"):
                    e.append(f"{f}: measure cần agg ({', '.join(AGGS)}) và column")
            for fl in (m.get("measure") or {}).get("filters", []) or []:
                if fl.get("op") not in ("eq", "in", "not_in") or "column" not in fl:
                    e.append(f"{f}: filter cần column và op eq/in/not_in")
        elif t == "ratio":
            for k in ("numerator", "denominator"):
                if not m.get(k):
                    e.append(f"{f}: ratio cần '{k}'")
        elif t == "derived":
            if not m.get("formula"):
                e.append(f"{f}: derived cần 'formula'")
            else:
                try:
                    tokens(m["formula"])
                except BuildError as exc:
                    e.append(f"{f}: {exc}")
        if t in ("ratio", "derived"):
            try:
                for r in refs(m):
                    if r not in lib.metrics:
                        e.append(f"{f}: tham chiếu chỉ số không tồn tại '{r}'")
            except BuildError:
                pass
    if e:
        return
    # vòng lặp tham chiếu
    state: dict[str, int] = {}

    def visit(n: str, path: list[str]) -> None:
        if state.get(n) == 2:
            return
        if state.get(n) == 1:
            e.append(f"{lib.files[n]}: vòng lặp tham chiếu: {' → '.join([*path, n])}")
            return
        state[n] = 1
        for r in refs(lib.metrics[n]):
            visit(r, [*path, n])
        state[n] = 2

    for n in lib.metrics:
        visit(n, [])
    if e:
        return
    # chiều có trên mart nguồn
    for name, m in lib.metrics.items():
        f = lib.files[name]
        cubes = realization_cubes(lib, name)
        allowed = component_dims(lib, name)
        for dname in m["dimensions"]:
            if not cubes and dname not in allowed:
                e.append(
                    f"{f}: chiều '{dname}' không có trên mọi thành phần (chỉ số khác mart chỉ được dùng giao các chiều)"
                )
            elif cubes and not any(c in lib.dimensions[dname]["columns"] for c in cubes):
                e.append(f"{f}: chiều '{dname}' không có trên mart nguồn ({', '.join(cubes)})")
        for dname in m.get("required_dimensions") or []:
            if dname not in m["dimensions"]:
                e.append(f"{f}: required_dimensions '{dname}' phải nằm trong dimensions")


def realization_cubes(lib: Library, name: str, memo: dict[str, list[str]] | None = None) -> list[str]:
    """Các mart mà chỉ số tính được hoàn toàn trong một cube."""
    memo = {} if memo is None else memo
    if name in memo:
        return memo[name]
    m = lib.metrics[name]
    if m["type"] == "simple":
        out = [m["source"], *[v["source"] for v in m.get("variants") or []]]
    else:
        sets = [set(realization_cubes(lib, r, memo)) for r in refs(m)]
        out = sorted(set.intersection(*sets)) if sets else []
        primary = [c for c in realization_cubes(lib, refs(m)[0], memo) if c in out]
        out = primary + [c for c in out if c not in primary]
    memo[name] = list(dict.fromkeys(out))
    return memo[name]


def metric_dims(lib: Library, name: str) -> set[str]:
    return set(lib.metrics[name]["dimensions"])


def component_dims(lib: Library, name: str) -> set[str]:
    m = lib.metrics[name]
    if m["type"] == "simple":
        return metric_dims(lib, name)
    sets = [metric_dims(lib, r) for r in refs(m)]
    return set.intersection(*sets) if sets else set()


# --------------------------------------------------------------------------- sinh Cube


def _filter_sql(fl: dict[str, Any]) -> str:
    def lit(v: Any) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        return "'" + str(v).replace("'", "''") + "'"

    col = "{CUBE}." + fl["column"]
    if fl["op"] == "eq":
        return f"{col} = {lit(fl['value'])}"
    vals = ", ".join(lit(v) for v in fl.get("values") or [fl.get("value")])
    return f"{col} {'IN' if fl['op'] == 'in' else 'NOT IN'} ({vals})"


def _cube_expr(lib: Library, name: str) -> str:
    m = lib.metrics[name]
    if m["type"] == "ratio":
        return f"1.0 * {{{m['numerator']}}} / NULLIF({{{m['denominator']}}}, 0)"
    out = []
    toks = tokens(m["formula"])
    for i, t in enumerate(toks):
        if re.match(r"^[a-z_]", t):
            out.append(f"{{{t}}}")
        elif t == "/" and i + 1 < len(toks):
            out.append("/")
        else:
            out.append(t)
    expr = " ".join(out)
    # chia cho 0 trả null (spec 03 §4.2)
    expr = re.sub(r"/ (\{[a-z_0-9]+\}|\([^()]*\))", r"/ NULLIF(\1, 0)", expr)
    return "1.0 * " + expr if "/" in expr else expr


def build_cubes(lib: Library) -> dict[str, dict[str, Any]]:
    cubes: dict[str, dict[str, Any]] = {}
    for mart, meta in lib.sources.items():
        dims = [
            {
                "name": meta["primary_key"],
                "sql": meta["primary_key"],
                "type": "string",
                "primary_key": True,
                "public": False,
            }
        ]
        for dname in sorted(lib.dimensions):
            dd = lib.dimensions[dname]
            col = dd["columns"].get(mart)
            if col and dname != meta["primary_key"]:
                dims.append({"name": dname, "sql": col, "type": dd["type"], "title": dd["name_vi"]})
        measures: list[dict[str, Any]] = []
        additive: list[str] = []
        for name in sorted(lib.metrics):
            m = lib.metrics[name]
            if mart not in realization_cubes(lib, name):
                continue
            if m["type"] == "simple":
                part = m if m["source"] == mart else next(v for v in m.get("variants") or [] if v["source"] == mart)
                ms = part["measure"]
                d = {"name": name, "type": AGGS[ms["agg"]], "sql": ms["column"], "title": m["name_vi"]}
                if ms.get("filters"):
                    d["filters"] = [{"sql": _filter_sql(fl)} for fl in ms["filters"]]
                if ms["agg"] in ADDITIVE:
                    additive.append(name)
            else:
                d = {"name": name, "type": "number", "sql": _cube_expr(lib, name), "title": m["name_vi"]}
            d["meta"] = {"version": m["version"], "unit": m["unit"]}
            measures.append(d)
        roll_dims = [d["name"] for d in dims if d["name"] in ("platform", "channel")]
        pre = []
        if additive:
            pre.append(
                {
                    "name": "daily",
                    "measures": additive,
                    "dimensions": roll_dims,
                    "time_dimension": "date",
                    "granularity": "day" if mart != "mrt_agency__budget_monthly" else "month",
                    # Không làm mới theo thời gian: đổi khi marts được hoán đổi (spec 03 §10.2).
                    "refresh_key": {
                        "sql": f"SELECT MAX(_dx_updated_at) FROM {{{{ COMPILE_CONTEXT.securityContext.dataset_prefix | safe }}}}_marts.{mart}"
                    },
                }
            )
            if mart == "mrt_seller__order_lines":
                pre.append(
                    {
                        "name": "by_product",
                        "measures": additive,
                        "dimensions": sorted({*roll_dims, "product", "product_name", "sku"}),
                        "time_dimension": "date",
                        "granularity": "day",
                        "refresh_key": pre[0]["refresh_key"],
                    }
                )
        cubes[mart] = {
            "name": mart,
            "sql_table": f"{{{{ COMPILE_CONTEXT.securityContext.dataset_prefix | safe }}}}_marts.{mart}",
            "title": meta["name_vi"],
            "dimensions": dims,
            "measures": measures,
            "pre_aggregations": pre,
        }
    cubes[STATUS_CUBE] = {
        "name": STATUS_CUBE,
        "sql_table": f"{{{{ COMPILE_CONTEXT.securityContext.dataset_prefix | safe }}}}_marts.{STATUS_CUBE}",
        "title": "Trạng thái dữ liệu",
        "dimensions": [
            {"name": "tenant_id", "sql": "tenant_id", "type": "string", "primary_key": True, "public": True},
            {"name": "data_as_of", "sql": "data_as_of", "type": "time"},
            {"name": "provisional_revenue_share", "sql": "provisional_revenue_share", "type": "number"},
            {"name": "missing_cogs_sku_count", "sql": "missing_cogs_sku_count", "type": "number"},
            {"name": "missing_cogs_revenue_vnd", "sql": "missing_cogs_revenue_vnd", "type": "number"},
            {"name": "run_id", "sql": "run_id", "type": "string"},
        ],
        "measures": [{"name": "rows", "type": "count"}],
        "pre_aggregations": [],
    }
    return cubes


# --------------------------------------------------------------------------- registry, sổ tay, ngữ cảnh AI


def describe_formula(lib: Library, name: str) -> str:
    m = lib.metrics[name]
    if m["type"] == "simple":
        ms = m["measure"]
        col = ms["column"]
        verb = {
            "sum": "Tổng",
            "count": "Số",
            "count_distinct": "Số",
            "avg": "Trung bình",
            "min": "Nhỏ nhất",
            "max": "Lớn nhất",
        }[ms["agg"]]
        src = lib.sources[m["source"]]["name_vi"].lower()
        text = f"{verb} {col.replace('_vnd', '').replace('_', ' ')} trên {src}"
        if ms.get("filters"):
            text += " (" + ", ".join(f"{f['column']} = {f.get('value', f.get('values'))}" for f in ms["filters"]) + ")"
        return text
    if m["type"] == "ratio":
        return f"{lib.metrics[m['numerator']]['name_vi']} ÷ {lib.metrics[m['denominator']]['name_vi']}"
    out = []
    for t in tokens(m["formula"]):
        out.append(lib.metrics[t]["name_vi"] if re.match(r"^[a-z_]", t) else {"*": "×", "/": "÷"}.get(t, t))
    return " ".join(out).replace("( ", "(").replace(" )", ")")


def build_registry(lib: Library) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in sorted(lib.metrics):
        m = lib.metrics[name]
        cubes = realization_cubes(lib, name)
        out[name] = {
            "metric": name,
            "name_vi": m["name_vi"],
            "description_vi": m["description_vi"],
            "version": m["version"],
            "type": m["type"],
            "unit": m["unit"],
            "good_direction": m["good_direction"],
            "packs": sorted(m["packs"]),
            "hidden": bool(m.get("hidden", False)),
            "requires": sorted(m.get("requires") or []),
            "dimensions": sorted(m["dimensions"]),
            "required_dimensions": sorted(m.get("required_dimensions") or []),
            "time_grains": [g for g in ("day", "week", "month") if g in m["time_grains"]],
            "mode": "cube" if cubes else "engine",
            "cube": cubes[0] if cubes else None,
            "measure": f"{cubes[0]}.{name}" if cubes else None,
            "realizations": {c: f"{c}.{name}" for c in cubes},
            "formula": (f"{m['numerator']} / {m['denominator']}" if m["type"] == "ratio" else m.get("formula")),
            "components": refs(m),
            "anomaly": m.get("anomaly"),
            "synonyms_vi": m.get("synonyms_vi") or [],
        }
    return out


def build_handbook(lib: Library) -> dict[str, Any]:
    items = []
    for name in sorted(lib.metrics):
        m = lib.metrics[name]
        if m.get("hidden"):
            continue
        items.append(
            {
                "metric": name,
                "name_vi": m["name_vi"],
                "description_vi": m["description_vi"],
                "formula_vi": describe_formula(lib, name),
                "source_note_vi": m["source_note_vi"],
                "unit": m["unit"],
                "version": m["version"],
                "history": m["history"],
                "synonyms_vi": m.get("synonyms_vi") or [],
                "packs": sorted(m["packs"]),
                "requires": sorted(m.get("requires") or []),
                "good_direction": m["good_direction"],
                "dimensions": [{"name": d, "name_vi": lib.dimensions[d]["name_vi"]} for d in sorted(m["dimensions"])],
                "time_grains": m["time_grains"],
            }
        )
    return {"metrics": items}


def build_ai_context(lib: Library) -> str:
    lines = [
        "# Thư viện chỉ số DataxLand (tự sinh – không sửa tay)",
        "",
        "| metric | Tên | Gói | Đơn vị | Phiên bản | Từ đồng nghĩa | Công thức |",
        "|---|---|---|---|---|---|---|",
    ]
    for name in sorted(lib.metrics):
        m = lib.metrics[name]
        if m.get("hidden"):
            continue
        lines.append(
            f"| `{name}` | {m['name_vi']} | {', '.join(m['packs'])} | {m['unit']} | {m['version']} | "
            f"{', '.join(m.get('synonyms_vi') or [])} | {describe_formula(lib, name)} |"
        )
    lines += ["", "## Chiều", ""] + [f"- `{d}`: {v['name_vi']}" for d, v in sorted(lib.dimensions.items())]
    return "\n".join(lines) + "\n"


def library_version(lib: Library) -> str:
    body = json.dumps({n: lib.metrics[n] for n in sorted(lib.metrics)}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def dump_yaml(obj: Any) -> str:
    return "# SINH RA bởi semantic/build.py – không sửa tay.\n" + yaml.safe_dump(
        obj, allow_unicode=True, sort_keys=True, width=200
    )


def run(root: Path = ROOT, out_root: Path | None = None) -> Library:
    out_root = out_root or root
    lib = load(root)
    validate(lib)
    if lib.errors:
        raise BuildError("\n".join(lib.errors))
    cubes = build_cubes(lib)
    model_dir = out_root / "cube" / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    for old in model_dir.glob("*.yml"):
        if old.stem not in cubes:
            old.unlink()
    for name, cube in cubes.items():
        (model_dir / f"{name}.yml").write_bytes(dump_yaml({"cubes": [cube]}).encode("utf-8"))
    dist = out_root / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    registry = {
        "library_version": library_version(lib),
        "metrics": build_registry(lib),
        "dimensions": {k: lib.dimensions[k] for k in sorted(lib.dimensions)},
        "cubes": {
            name: {
                "dimensions": {d["name"]: d["sql"] for d in c["dimensions"]},
                "measures": sorted(ms["name"] for ms in c["measures"]),
            }
            for name, c in sorted(cubes.items())
        },
        "status_cube": STATUS_CUBE,
    }
    (dist / "metrics.json").write_bytes(
        (json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    (dist / "handbook.json").write_bytes(
        (json.dumps(build_handbook(lib), ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    (dist / "ai_context.md").write_bytes(build_ai_context(lib).encode("utf-8"))
    return lib


def main() -> int:
    try:
        lib = run()
    except BuildError as exc:
        print("semantic/build.py: thư viện chỉ số không hợp lệ:\n" + str(exc), file=sys.stderr)
        return 1
    print(f"semantic/build.py: {len(lib.metrics)} chỉ số, {len(lib.sources) + 1} cube")
    return 0


if __name__ == "__main__":
    sys.exit(main())
