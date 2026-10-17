"""Ba công cụ chỉ đọc của AI hỏi đáp (spec 09 §2), dùng chung cho MCP server và bộ máy hỏi đáp của API.

Khách và quyền không bao giờ là tham số: chúng nằm trong token phiên do API ký (`MCP_SESSION_SECRET`).
Không có công cụ chạy SQL hay ghi dữ liệu.
"""

from __future__ import annotations

from typing import Any

MAX_TOOL_ROWS = 200
SESSION_HEADER = "X-Dx-Session"

_TIME = {
    "type": "object",
    "description": (
        "Khoảng thời gian: {preset} với preset là today, yesterday, this_week, last_week, this_month, "
        "last_month, last_7_days, last_30_days, last_90_days; hoặc {from, to} dạng YYYY-MM-DD."
    ),
    "properties": {
        "preset": {"type": "string"},
        "from": {"type": "string"},
        "to": {"type": "string"},
    },
    "additionalProperties": False,
}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_metrics",
        "description": "Danh sách chỉ số người hỏi được xem: tên, tên tiếng Việt, đơn vị, chiều được phép.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "describe_metric",
        "description": "Mô tả một chỉ số: định nghĩa, công thức, phiên bản, chiều và độ chi tiết thời gian.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Mã chỉ số, ví dụ net_revenue"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "query_metric",
        "description": (
            "Truy vấn số từ thư viện chỉ số. Trả rows, metrics (tên, phiên bản, đơn vị), data_as_of, warnings. "
            f"Tối đa {MAX_TOOL_ROWS} dòng."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metrics": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "dimensions": {"type": "array", "items": {"type": "string"}},
                "time": _TIME,
                "grain": {"type": "string", "enum": ["day", "week", "month", "none"]},
                "filters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "dimension": {"type": "string"},
                            "op": {"type": "string", "enum": ["eq", "in", "not_in"]},
                            "value": {},
                            "values": {"type": "array"},
                        },
                        "required": ["dimension", "op"],
                    },
                },
                "compare": {"type": "string", "enum": ["previous_period", "trailing_4_weeks"]},
            },
            "required": ["metrics"],
            "additionalProperties": False,
        },
    },
]

TOOL_NAMES = frozenset(t["name"] for t in TOOLS)
QUERY_FIELDS = ("metrics", "dimensions", "time", "grain", "filters", "compare")


def clean_query_args(args: dict[str, Any]) -> dict[str, Any]:
    """Chỉ giữ tham số hợp lệ của `query_metric`; tham số lạ (vd. `tenant_id` do model tự thêm) bị bỏ."""
    out = {k: args[k] for k in QUERY_FIELDS if k in args and args[k] is not None}
    out.setdefault("dimensions", [])
    return out


def shape_result(res: dict[str, Any]) -> dict[str, Any]:
    """Kết quả trả cho model (spec 09 §2): rows, metrics, data_as_of, warnings, time; cắt ở 200 dòng."""
    rows = list(res.get("rows") or [])
    out: dict[str, Any] = {
        "time": res.get("time"),
        "metrics": res.get("metrics") or {},
        "rows": rows[:MAX_TOOL_ROWS],
        "data_as_of": res.get("data_as_of"),
        "warnings": res.get("warnings") or [],
    }
    if len(rows) > MAX_TOOL_ROWS:
        out["truncated"] = f"Kết quả có {len(rows)} dòng, chỉ trả {MAX_TOOL_ROWS} dòng đầu"
    return out
