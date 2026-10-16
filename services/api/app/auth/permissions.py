"""Ma trận quyền theo hành động (FR-AUTH-02, spec 05 §4). Router gọi `require(ctx, "<action>")`.

Giá trị của ô:
- `True`: được phép.
- `"budgets"`: chỉ với ngân sách quảng cáo (partner với `inputs.*`).
- `"scoped"`: được phép, phạm vi chỉ số lọc thêm ở bộ máy chỉ số (member, partner, group).
- `"agency"`: chỉ báo cáo gói agency (partner với `reports.read`).
- `"summary"`: chỉ tin tóm tắt (group với `reports.read`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from app.errors import ApiError

if TYPE_CHECKING:
    from app.auth.context import AuthContext

Role = Literal["owner", "member", "partner", "data_lead", "engineer", "group"]
ROLES: tuple[Role, ...] = ("owner", "member", "partner", "data_lead", "engineer", "group")

Cell = bool | str

MATRIX: dict[str, dict[str, Cell]] = {
    "metrics.read": {
        "owner": True,
        "member": "scoped",
        "partner": "scoped",
        "data_lead": True,
        "engineer": True,
        "group": "scoped",
    },
    "reports.read": {
        "owner": True,
        "member": True,
        "partner": "agency",
        "data_lead": True,
        "engineer": True,
        "group": "summary",
    },
    "reports.edit": {"data_lead": True},
    "reports.approve": {"data_lead": True},
    "inputs.read": {"owner": True, "member": True, "partner": "budgets", "data_lead": True, "engineer": True},
    "inputs.write": {"owner": True, "partner": "budgets", "data_lead": True},
    "decisions.read": {"owner": True, "member": True, "partner": True, "data_lead": True, "engineer": True},
    "decisions.write": {"owner": True, "partner": True, "data_lead": True},
    "users.manage": {"owner": True, "data_lead": True},
    "partners.manage": {"owner": True},
    "telegram.link_self": {"owner": True, "member": True, "partner": True, "data_lead": True, "engineer": True},
    "telegram.link_group": {"owner": True},
    "telegram.manage": {"owner": True},
    "connect.sources": {"data_lead": True},
    "ops.read": {"data_lead": True, "engineer": True},
    "ops.write": {"data_lead": True},
    "healthchecks.review": {"data_lead": True},
}

ACTIONS = tuple(MATRIX)


def cell(role: str, action: str) -> Cell:
    try:
        return MATRIX[action].get(role, False)
    except KeyError as exc:
        raise ValueError(f"hành động không có trong ma trận: {action}") from exc


def allowed(role: str, action: str, *, resource: str | None = None, pack: str | None = None) -> bool:
    c = cell(role, action)
    if c is True or c == "scoped" or c == "summary":
        return True
    if c == "budgets":
        return resource == "ad_budgets"
    if c == "agency":
        return pack == "agency"
    return False


def require(ctx: AuthContext, action: str, *, resource: str | None = None) -> None:
    if not allowed(ctx.role, action, resource=resource, pack=ctx.pack):
        raise ApiError(403, "PERMISSION_DENIED", f"Vai trò {ctx.role} không được thực hiện {action}")
