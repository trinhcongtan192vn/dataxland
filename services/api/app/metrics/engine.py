"""Bộ máy truy vấn chỉ số (FR-MET-05, FR-MET-06, spec 03 §4.2).

1. Kiểm tra quyền xem từng chỉ số (§4.4).
2. Phân rã mỗi chỉ số thành các measure Cube; chọn mart có đủ chiều được hỏi. Nhóm measure theo cube.
3. Gọi Cube một lần cho mỗi cube, cùng khoảng thời gian, `grain` và chiều; có `compare` thì gọi thêm cho kỳ so sánh.
4. Ghép kết quả theo giá trị chiều (thiếu là 0 với `simple`).
5. Áp công thức `ratio`, `derived` khác mart bằng bộ phân tích biểu thức an toàn. Chia cho 0 trả null.
6. Thêm `warnings` từ `mrt_common__data_status` khi chỉ số trong yêu cầu bị ảnh hưởng.
7. Ghi `metric_queries` (không ghi giá trị trả về).

Khách luôn lấy từ `AuthContext`, không lấy từ body (spec 05 §3).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from operator import itemgetter
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.context import AuthContext
from app.errors import ApiError
from app.metrics import expr
from app.metrics.cube_client import get_cube
from app.metrics.periods import Period, previous_period, resolve, trailing_periods
from app.metrics.registry import MetricDef, Registry, get_registry
from dx_common.ids import new_ulid
from dx_common.money import format_vnd, round_vnd
from dx_common.timeutil import iso_z, now_utc

MAX_METRICS, MAX_DIMS, MAX_ROWS = 10, 3, 5000
SELLER_PACK_WARNING = "PROVISIONAL"
MISSING_COGS_METRICS = {"cogs", "contribution_margin", "net_profit_after_fees", "net_margin_pct", "sku_profit"}


class FilterIn(BaseModel):
    dimension: str
    op: Literal["eq", "in", "not_in"]
    values: list[Any] = Field(default_factory=list)
    value: Any = None

    def vals(self) -> list[Any]:
        return self.values if self.values else ([self.value] if self.value is not None else [])


class OrderIn(BaseModel):
    metric: str
    dir: Literal["asc", "desc"] = "desc"


class QueryIn(BaseModel):
    metrics: list[str] = Field(min_length=1)
    dimensions: list[str] = Field(default_factory=list)
    time: dict[str, str] | None = None
    grain: Literal["day", "week", "month", "none"] = "none"
    filters: list[FilterIn] = Field(default_factory=list)
    compare: Literal["previous_period", "trailing_4_weeks"] | None = None
    order: list[OrderIn] = Field(default_factory=list)
    limit: int = Field(default=1000, ge=1, le=MAX_ROWS)


@dataclass
class DataStatus:
    data_as_of: datetime | None = None
    provisional_share: Decimal = Decimal(0)
    missing_sku_count: int = 0
    missing_revenue: Decimal = Decimal(0)


@dataclass
class Leaf:
    name: str
    cube: str
    per_entity: dict[str, Any] | None = None


@dataclass
class Node:
    name: str
    leaf: Leaf | None = None
    formula: str | None = None
    children: list[Node] = field(default_factory=list)


# --------------------------------------------------------------------------- quyền xem chỉ số (§4.4)


def can_view(ctx: AuthContext, m: MetricDef, reg: Registry, *, allow_hidden: bool = False) -> bool:
    if m.hidden and not allow_hidden:
        return False
    if not reg.tenant_eligible(m, ctx.tenant):
        return False
    role = ctx.role
    if role in ("owner", "data_lead", "engineer", "internal"):
        return True
    if role == "member":
        return ctx.metric_scope == "all" or m.metric in ctx.metric_scope
    if role == "partner":
        return "agency" in m.packs
    if role == "group":
        return ctx.metric_scope != "all" and m.metric in ctx.metric_scope
    return False


def visible_metrics(ctx: AuthContext) -> list[MetricDef]:
    reg = get_registry()
    return [m for m in reg.visible_for_tenant(ctx.tenant) if can_view(ctx, m, reg)]


def check_metric(ctx: AuthContext, name: str, *, allow_hidden: bool = False) -> MetricDef:
    reg = get_registry()
    m = reg.get(name)
    if m is None or (m.hidden and not allow_hidden):
        raise ApiError(400, "METRIC_UNKNOWN", f"Không có chỉ số {name}")
    if not reg.tenant_eligible(m, ctx.tenant):
        raise ApiError(403, "METRIC_FORBIDDEN", f"Chỉ số {name} không thuộc gói hoặc điều kiện của khách")
    if not can_view(ctx, m, reg, allow_hidden=allow_hidden):
        raise ApiError(403, "METRIC_FORBIDDEN", f"Bạn không được xem chỉ số {name}")
    return m


# --------------------------------------------------------------------------- phân rã


def _cube_for(reg: Registry, m: MetricDef, dims: set[str]) -> str | None:
    """Mart đầu tiên (ưu tiên mart chính) tính được chỉ số và có đủ các chiều được hỏi."""
    for cube in m.realizations:
        if dims <= set(reg.cubes.get(cube, {}).get("dimensions", {})):
            return cube
    return None


def build_node(reg: Registry, name: str, dims: set[str]) -> Node:
    m = reg.get(name)
    if m is None:
        raise ApiError(400, "METRIC_UNKNOWN", f"Không có chỉ số {name}")
    if m.per_entity:
        base = reg.get(str(m.per_entity["base"]))
        base_cube = _cube_for(reg, base, dims | {str(m.per_entity["dimension"])}) if base else None
        if base_cube is None:
            raise ApiError(400, "DIMENSION_NOT_ALLOWED", f"Chỉ số {name} không cắt được theo {', '.join(sorted(dims))}")
        return Node(name, leaf=Leaf(name, base_cube, m.per_entity))
    cube = _cube_for(reg, m, dims)
    if cube:
        return Node(name, leaf=Leaf(name, cube))
    if m.type == "simple" or not m.formula:
        raise ApiError(400, "DIMENSION_NOT_ALLOWED", f"Chỉ số {name} không cắt được theo {', '.join(sorted(dims))}")
    return Node(name, formula=m.formula, children=[build_node(reg, c, dims) for c in m.components])


def leaves(node: Node) -> list[Leaf]:
    if node.leaf:
        return [node.leaf]
    return [lf for ch in node.children for lf in leaves(ch)]


# --------------------------------------------------------------------------- gọi Cube


def _to_dec(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _cube_filter(cube: str, f: FilterIn, reg: Registry) -> dict[str, Any]:
    member = f"{cube}.{f.dimension}"
    vals = [("true" if v else "false") if isinstance(v, bool) else str(v) for v in f.vals()]
    if reg.dimension_type(f.dimension) == "boolean":
        vals = ["true" if str(v).lower() in ("true", "1") else "false" for v in vals]
    return {"member": member, "operator": "notEquals" if f.op == "not_in" else "equals", "values": vals}


def run_period(
    ctx: AuthContext,
    reg: Registry,
    leaf_list: list[Leaf],
    dims: list[str],
    period: Period,
    grain: str,
    filters: list[FilterIn],
) -> dict[tuple[Any, ...], dict[str, Decimal | None]]:
    by_cube: dict[str, list[str]] = {}
    per_entity = [lf for lf in leaf_list if lf.per_entity]
    leaf_list = [lf for lf in leaf_list if not lf.per_entity]
    for lf in leaf_list:
        by_cube.setdefault(lf.cube, [])
        if lf.name not in by_cube[lf.cube]:
            by_cube[lf.cube].append(lf.name)
    merged: dict[tuple[Any, ...], dict[str, Decimal | None]] = {}
    cube = get_cube()
    for cube_name, measures in by_cube.items():
        td: dict[str, Any] = {
            "dimension": f"{cube_name}.date",
            "dateRange": [period.start.isoformat(), period.end.isoformat()],
        }
        if grain != "none":
            td["granularity"] = grain
        q: dict[str, Any] = {
            "measures": [f"{cube_name}.{m}" for m in measures],
            "dimensions": [f"{cube_name}.{d}" for d in dims],
            "timeDimensions": [td],
            "filters": [_cube_filter(cube_name, f, reg) for f in filters],
            "limit": MAX_ROWS,
            "timezone": "UTC",
        }
        for row in cube.load(ctx.tenant_id, ctx.dataset_prefix, q):
            key_parts: list[Any] = []
            if grain != "none":
                raw = row.get(f"{cube_name}.date.{grain}") or row.get(f"{cube_name}.date")
                key_parts.append(str(raw)[:10] if raw else None)
            for d in dims:
                v = row.get(f"{cube_name}.{d}")
                if reg.dimension_type(d) == "boolean" and v is not None:
                    v = str(v).lower() in ("true", "1")
                key_parts.append(v)
            key = tuple(key_parts)
            vals = merged.setdefault(key, {})
            for m in measures:
                vals[m] = _to_dec(row.get(f"{cube_name}.{m}"))
    for lf in per_entity:
        _run_per_entity(ctx, reg, lf, dims, period, grain, filters, merged)
    return merged


def _run_per_entity(
    ctx: AuthContext,
    reg: Registry,
    lf: Leaf,
    dims: list[str],
    period: Period,
    grain: str,
    filters: list[FilterIn],
    merged: dict[tuple[Any, ...], dict[str, Decimal | None]],
) -> None:
    """Tổng hợp hai bậc: lấy `base` theo từng thực thể (vd. số đơn mỗi người mua) rồi đếm thực thể đạt `min`."""
    pe = lf.per_entity or {}
    base, entity, minimum = str(pe["base"]), str(pe["dimension"]), Decimal(str(pe["min"]))
    sub = run_period(ctx, reg, [Leaf(base, lf.cube)], [*dims, entity], period, grain, filters)
    counts: dict[tuple[Any, ...], int] = {}
    for key, vals in sub.items():
        outer = key[:-1]  # bỏ phần thực thể ở cuối khóa
        counts.setdefault(outer, 0)
        v = vals.get(base)
        if key[-1] is not None and v is not None and v >= minimum:
            counts[outer] += 1
    for outer, n in counts.items():
        merged.setdefault(outer, {})[lf.name] = Decimal(n)


def evaluate(node: Node, vals: dict[str, Decimal | None], reg: Registry) -> Decimal | None:
    if node.leaf:
        v = vals.get(node.name)
        m = reg.get(node.name)
        if v is None and m is not None and m.type == "simple":
            return Decimal(0)
        return v
    child_vals = {ch.name: evaluate(ch, vals, reg) for ch in node.children}
    return expr.evaluate(node.formula or "", child_vals)


def format_value(v: Decimal | None, unit: str) -> int | float | None:
    if v is None:
        return None
    if unit == "VND":
        return round_vnd(v)
    if unit == "count":
        iv = int(v)
        return iv if v == iv else round(float(v), 4)
    return round(float(v), 6)


# --------------------------------------------------------------------------- trạng thái dữ liệu


def data_status(ctx: AuthContext) -> DataStatus:
    cube = get_registry().status_cube
    q = {
        "dimensions": [
            f"{cube}.data_as_of",
            f"{cube}.provisional_revenue_share",
            f"{cube}.missing_cogs_sku_count",
            f"{cube}.missing_cogs_revenue_vnd",
        ],
        "limit": 1,
        "timezone": "UTC",
    }
    try:
        rows = get_cube().load(ctx.tenant_id, ctx.dataset_prefix, q)
    except ApiError:
        return DataStatus()
    if not rows:
        return DataStatus()
    r = rows[0]
    raw = r.get(f"{cube}.data_as_of")
    as_of = datetime.fromisoformat(str(raw).replace("Z", "")).replace(tzinfo=None) if raw else None
    from datetime import UTC

    return DataStatus(
        data_as_of=as_of.replace(tzinfo=UTC) if as_of else None,
        provisional_share=_to_dec(r.get(f"{cube}.provisional_revenue_share")) or Decimal(0),
        missing_sku_count=int(_to_dec(r.get(f"{cube}.missing_cogs_sku_count")) or 0),
        missing_revenue=_to_dec(r.get(f"{cube}.missing_cogs_revenue_vnd")) or Decimal(0),
    )


def warnings_for(ctx: AuthContext, metrics: list[str], status: DataStatus) -> list[dict[str, Any]]:
    """MISSING_COGS, PROVISIONAL, STALE (FR-INP-03, spec 03 §4.3)."""
    reg = get_registry()
    out: list[dict[str, Any]] = []
    affected = sorted(set(metrics) & MISSING_COGS_METRICS)
    if status.missing_sku_count > 0 and affected:
        out.append(
            {
                "code": "MISSING_COGS",
                "detail_vi": f"{status.missing_sku_count} SKU chưa có giá vốn, chiếm {format_vnd(status.missing_revenue)} doanh thu",
                "metrics": affected,
                "action_url": "/app/inputs/costs",
            }
        )
    seller_metrics = [m for m in metrics if (md := reg.get(m)) and "seller" in md.packs and ctx.pack == "seller"]
    if status.provisional_share > 0 and seller_metrics:
        pct = (status.provisional_share * 100).quantize(Decimal("1"))
        out.append(
            {
                "code": "PROVISIONAL",
                "detail_vi": f"{pct}% doanh thu trong 30 ngày gần nhất là tạm tính, chưa quyết toán",
            }
        )
    if status.data_as_of is not None:
        fresh = timedelta(hours=ctx.tenant.quality.freshness_hours or 8)
        if now_utc() - status.data_as_of > fresh:
            out.append({"code": "STALE", "detail_vi": "Dữ liệu cũ hơn ngưỡng độ tươi; số có thể chưa cập nhật"})
    return out


# --------------------------------------------------------------------------- truy vấn


def query(
    ctx: AuthContext,
    body: QueryIn,
    *,
    db: Session | None = None,
    allow_hidden: bool = False,
    caller: str = "api",
    today: date | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    reg = get_registry()
    if len(body.metrics) > MAX_METRICS:
        raise ApiError(400, "TOO_MANY_METRICS", f"Tối đa {MAX_METRICS} chỉ số mỗi truy vấn")
    if len(body.dimensions) > MAX_DIMS:
        raise ApiError(400, "TOO_MANY_DIMENSIONS", f"Tối đa {MAX_DIMS} chiều mỗi truy vấn")
    defs = [check_metric(ctx, m, allow_hidden=allow_hidden) for m in dict.fromkeys(body.metrics)]
    filter_dims = {f.dimension for f in body.filters}
    internal = [d for d in [*body.dimensions, *filter_dims] if reg.is_internal_dimension(d)]
    if internal:
        raise ApiError(400, "DIMENSION_NOT_ALLOWED", f"Không cắt được theo {', '.join(internal)}")
    for m in defs:
        bad = [d for d in [*body.dimensions, *filter_dims] if d not in m.dimensions]
        if bad:
            raise ApiError(400, "DIMENSION_NOT_ALLOWED", f"Chỉ số {m.metric} không cắt được theo {', '.join(bad)}")
        if body.grain != "none" and body.grain not in m.time_grains:
            raise ApiError(400, "GRAIN_NOT_ALLOWED", f"Chỉ số {m.metric} không có grain {body.grain}")
        missing_req = [d for d in m.required_dimensions if d not in body.dimensions]
        if missing_req:
            raise ApiError(400, "DIMENSION_REQUIRED", f"Chỉ số {m.metric} cần chiều {', '.join(missing_req)}")
    period = resolve(body.time, today)
    need = set(body.dimensions) | filter_dims
    nodes = [build_node(reg, m.metric, need) for m in defs]
    all_leaves = [lf for n in nodes for lf in leaves(n)]
    status_ok = "ok"
    try:
        cur = run_period(ctx, reg, all_leaves, body.dimensions, period, body.grain, body.filters)
        cmp_rows: dict[tuple[Any, ...], dict[str, Decimal | None]] | None = None
        if body.compare == "previous_period":
            pp = previous_period(period)
            raw = run_period(ctx, reg, all_leaves, body.dimensions, pp, body.grain, body.filters)
            cmp_rows = _realign(raw, body.grain, period, pp)
        elif body.compare == "trailing_4_weeks":
            cmp_rows = _average(
                [
                    _realign(
                        run_period(ctx, reg, all_leaves, body.dimensions, tp, body.grain, body.filters),
                        body.grain,
                        period,
                        tp,
                    )
                    for tp in trailing_periods(period)
                ],
                nodes,
                reg,
            )
    except ApiError:
        status_ok = "error"
        raise
    finally:
        _log(db, ctx, body, period, int((time.perf_counter() - started) * 1000), status_ok, caller)

    rows: list[dict[str, Any]] = []
    for key in sorted(cur, key=lambda k: tuple("" if x is None else str(x) for x in k)):
        row: dict[str, Any] = {}
        parts = list(key)
        if body.grain != "none":
            row["date"] = parts.pop(0)
        for d, v in zip(body.dimensions, parts, strict=True):
            row[d] = v
        for n, md in zip(nodes, defs, strict=True):
            row[md.metric] = format_value(evaluate(n, cur[key], reg), md.unit)
        if cmp_rows is not None:
            cv = cmp_rows.get(key, {})
            row["compare"] = {
                md.metric: format_value(evaluate(n, cv, reg) if cv else None, md.unit)
                for n, md in zip(nodes, defs, strict=True)
            }
        rows.append(row)
    for o in reversed(body.order):
        present = [r for r in rows if r.get(o.metric) is not None]
        missing = [r for r in rows if r.get(o.metric) is None]
        present.sort(key=itemgetter(o.metric), reverse=o.dir == "desc")
        rows = present + missing  # giá trị trống luôn ở cuối
    rows = rows[: body.limit]
    status = data_status(ctx)
    return {
        "query_id": new_ulid(),
        "tenant_id": ctx.tenant_id,
        "time": {"from": period.start.isoformat(), "to": period.end.isoformat(), "grain": body.grain},
        "metrics": {md.metric: {"name_vi": md.name_vi, "version": md.version, "unit": md.unit} for md in defs},
        "rows": rows,
        "data_as_of": iso_z(status.data_as_of) if status.data_as_of else None,
        "warnings": warnings_for(ctx, [m.metric for m in defs], status),
    }


def _realign(
    raw: dict[tuple[Any, ...], dict[str, Decimal | None]], grain: str, cur: Period, other: Period
) -> dict[tuple[Any, ...], dict[str, Decimal | None]]:
    """Đưa khóa của kỳ so sánh về khóa của kỳ hiện tại (dời mốc thời gian theo độ lệch hai kỳ)."""
    if grain == "none":
        return raw
    shift = (cur.start - other.start).days
    out: dict[tuple[Any, ...], dict[str, Decimal | None]] = {}
    for k, v in raw.items():
        if k[0]:
            d = date.fromisoformat(k[0]) + timedelta(days=shift)
            out[(d.isoformat(), *k[1:])] = v
    return out


def _average(
    maps: list[dict[tuple[Any, ...], dict[str, Decimal | None]]], nodes: list[Node], reg: Registry
) -> dict[tuple[Any, ...], dict[str, Decimal | None]]:
    keys = {k for m in maps for k in m}
    out: dict[tuple[Any, ...], dict[str, Decimal | None]] = {}
    for k in keys:
        leaf_names = {lf.name for n in nodes for lf in leaves(n)}
        avg: dict[str, Decimal | None] = {}
        for name in leaf_names:
            vals = [m.get(k, {}).get(name) or Decimal(0) for m in maps]
            avg[name] = sum(vals, Decimal(0)) / Decimal(len(maps))
        out[k] = avg
    return out


def _log(
    db: Session | None, ctx: AuthContext, body: QueryIn, period: Period, ms: int, status: str, caller: str
) -> None:
    """Nhật ký truy vấn để truy vết (NFR-10). Không ghi giá trị trả về."""
    if db is None:
        return
    from app.db.models import MetricQuery

    db.add(
        MetricQuery(
            query_id=new_ulid(),
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            caller=caller,
            metrics=list(body.metrics),
            dimensions=list(body.dimensions),
            time_from=period.start,
            time_to=period.end,
            duration_ms=ms,
            status=status,
        )
    )


# --------------------------------------------------------------------------- tiện ích cho nhập liệu


def selling_skus(ctx: AuthContext, db: Session | None = None) -> list[tuple[str, str]]:
    """SKU đang bán 90 ngày qua, sắp theo doanh thu (cho mẫu Excel giá vốn, spec 05 §6.4)."""
    if ctx.pack != "seller":
        return []
    res = query(
        ctx,
        QueryIn(
            metrics=["line_net_revenue"],
            dimensions=["sku", "product_name"],
            time={"preset": "last_90_days"},
            order=[OrderIn(metric="line_net_revenue")],
            limit=5000,
        ),
        db=db,
        allow_hidden=True,
        caller="inputs",
    )
    return [(str(r["sku"]), str(r.get("product_name") or "")) for r in res["rows"] if r.get("sku")]


def missing_cogs_skus(ctx: AuthContext, db: Session | None = None) -> tuple[list[dict[str, Any]], str | None]:
    """SKU có doanh thu 30 ngày mà chưa có giá vốn (FR-INP-03), qua mart dòng đơn với `has_missing_cogs`."""
    if ctx.pack != "seller":
        return [], None
    res = query(
        ctx,
        QueryIn(
            metrics=["missing_cogs_revenue"],
            dimensions=["sku", "product_name"],
            time={"preset": "last_30_days"},
            order=[OrderIn(metric="missing_cogs_revenue")],
            limit=500,
        ),
        db=db,
        allow_hidden=True,
        caller="inputs",
    )
    items = [
        {"seller_sku": r["sku"], "product_name": r.get("product_name"), "net_revenue_30d": r["missing_cogs_revenue"]}
        for r in res["rows"]
        if (r.get("missing_cogs_revenue") or 0) > 0
    ]
    return items, res["data_as_of"]
