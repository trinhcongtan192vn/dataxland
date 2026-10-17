"""Chi phí GCP theo khách (spec 04 §6, FR-OPS-06, NFR-08).

Đọc billing export của GCP trên BigQuery (`GCP_BILLING_EXPORT_TABLE`), cộng chi phí đã trừ khuyến mãi theo nhãn
`tenant_id` của tháng hóa đơn, quy sang VND bằng tỷ giá gần nhất trong `dx_ref.fx_rates`, rồi gửi
`POST /v1/internal/costs` (mục `gcp`). Chi phí không có nhãn khách không chia cho khách nào.
"""

import re
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

import dagster as dg

from dx_common.config import get_settings
from dx_common.timeutil import add_months, month_start, today_vn

TABLE_RE = re.compile(r"^[a-z][a-z0-9\-]{4,61}[a-z0-9]\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")


class _Query(Protocol):
    def query(self, sql: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]: ...


class _Api(Protocol):
    def post(self, path: str, body: dict[str, Any] | None = None) -> Any: ...


def billing_sql(table: str, month: date) -> str:
    """SQL riêng của BigQuery (billing export không có ở DuckDB); bảng và tháng đã kiểm tra định dạng."""
    if not TABLE_RE.match(table):
        raise ValueError("GCP_BILLING_EXPORT_TABLE phải có dạng project.dataset.table")
    invoice_month = month.strftime("%Y%m")
    return (
        "select l.value as tenant_id, any_value(currency) as currency, "
        "sum(cost) + sum(ifnull((select sum(c.amount) from unnest(credits) as c), 0)) as amount "
        f"from `{table}`, unnest(labels) as l "
        f"where l.key = 'tenant_id' and invoice.month = '{invoice_month}' "
        "group by 1"
    )


def usd_rate(wh: _Query) -> Decimal | None:
    rows = wh.query("select rate_vnd from dx_ref.fx_rates where currency = 'USD' order by date desc limit 1")
    return Decimal(str(rows[0][0])) if rows and rows[0][0] is not None else None


def gcp_cost_rows(wh: _Query, table: str, month: date) -> list[dict[str, Any]]:
    rate = usd_rate(wh)
    out: list[dict[str, Any]] = []
    for tenant_id, currency, amount in wh.query(billing_sql(table, month)):
        amt = Decimal(str(amount or 0))
        if currency and currency != "VND":
            if currency != "USD" or rate is None:
                raise ValueError(f"Không quy đổi được {currency} sang VND")
            amt = amt * rate
        out.append({"tenant_id": str(tenant_id), "amount_vnd": str(amt.quantize(Decimal("0.01")))})
    return out


def run_gcp_costs(wh: _Query, api: _Api, table: str, today: date | None = None) -> dict[str, Any]:
    """Tháng này và tháng trước (hóa đơn tháng trước còn điều chỉnh vài ngày đầu tháng)."""
    cur = month_start(today or today_vn())
    res: dict[str, Any] = {}
    for m in (add_months(cur, -1), cur):
        rows = gcp_cost_rows(wh, table, m)
        api.post("/v1/internal/costs", {"month": m.strftime("%Y-%m"), "item": "gcp", "rows": rows})
        res[m.strftime("%Y-%m")] = len(rows)
    return res


@dg.op
def gcp_costs_op(context: dg.OpExecutionContext) -> dict[str, Any]:
    from dx_pipelines.api_client import ApiClient
    from dx_pipelines.warehouse import get_warehouse

    table = get_settings().gcp_billing_export_table
    if not table:
        context.log.info("Chưa cấu hình GCP_BILLING_EXPORT_TABLE, bỏ qua")
        return {"skipped": True}
    res = run_gcp_costs(get_warehouse(job="costs"), ApiClient(), table)
    context.log.info(str(res))
    return res


@dg.job(description="Chi phí GCP theo khách từ billing export (FR-OPS-06)")
def gcp_costs() -> None:
    gcp_costs_op()
