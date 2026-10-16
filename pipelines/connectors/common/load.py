"""Chạy connector qua dlt (spec 01 §1, §2): ghi `merge` theo khóa chính vào `t_<tenant>_raw`, thêm ba cột hợp đồng,
lưu con trỏ trong dlt state.

Connector cung cấp danh sách `Table` (tên bảng, khóa, hàm sinh bản ghi). Mỗi hàm sinh nhận `state` (dict trong dlt
state của nguồn, theo tài khoản) để đọc và ghi con trỏ.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from connectors.base import SourceError, SyncContext, SyncOutcome, with_contract
from dx_common.tenants import SourceConfig, TenantConfig

HISTORY_DAYS = 90
WINDOW_DAYS = 7
RESCAN_DAYS = 30
CURSOR_OVERLAP = timedelta(minutes=30)

RowFn = Callable[[dict[str, Any]], Iterable[dict[str, Any]]]


@dataclass
class Table:
    name: str  # `<source>__<object>`
    primary_key: list[str]
    rows: RowFn
    schema: dict[str, str]  # cột → kiểu (`string`, `int`, `numeric`, `date`, `timestamp`, `bool`, `float`)


_DLT_TYPES = {
    "string": "text",
    "int": "bigint",
    "numeric": "decimal",
    "date": "date",
    "timestamp": "timestamp",
    "bool": "bool",
    "float": "double",
}
CONTRACT_SCHEMA = {"_dx_loaded_at": "timestamp", "_dx_source_account": "string", "_dx_record_hash": "string"}


def dlt_columns(schema: dict[str, str]) -> dict[str, dict[str, Any]]:
    return {c: {"data_type": _DLT_TYPES[t], "nullable": True} for c, t in {**schema, **CONTRACT_SCHEMA}.items()}


def _source_error(exc: BaseException) -> SourceError | None:
    cur: BaseException | None = exc
    seen = 0
    while cur is not None and seen < 10:
        if isinstance(cur, SourceError):
            return cur
        cur = cur.__cause__ or cur.__context__
        seen += 1
    return None


def windows(start: datetime, end: datetime, days: int = WINDOW_DAYS) -> Iterator[tuple[datetime, datetime]]:
    """Chia [start, end) thành cửa sổ `days` ngày (FR-ING-05)."""
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=days), end)
        yield cur, nxt
        cur = nxt


def cursor_start(state: dict[str, Any], key: str, now: datetime) -> tuple[datetime, bool]:
    """Điểm bắt đầu nạp: con trỏ trừ một khoảng chồng lấn, hoặc 90 ngày trước nếu chưa có (lần đầu)."""
    raw = state.get(key)
    if raw is None:
        return now - timedelta(days=HISTORY_DAYS), True
    return datetime.fromtimestamp(int(raw), tz=now.tzinfo) - CURSOR_OVERLAP, False


def _destination(ctx: SyncContext) -> Any:
    import dlt

    wh = ctx.warehouse
    if wh.kind == "duckdb":
        return dlt.destinations.duckdb(credentials=str(wh.path))
    # pragma: no cover - cần BigQuery thật. Dùng đúng credentials (đã impersonate service account của khách).
    return dlt.destinations.bigquery(credentials=wh.client._credentials, location=wh.location)


def run_tables(tenant: TenantConfig, source: SourceConfig, ctx: SyncContext, tables: list[Table]) -> SyncOutcome:
    account = source.account_id or ""
    name = f"{tenant.tenant_id}__{source.type}__{account}"
    return run_dlt(name, source.type, ctx.raw_dataset, account, ctx, tables)


def run_dlt(
    pipeline_name: str, source_name: str, dataset: str, account: str, ctx: SyncContext, tables: list[Table]
) -> SyncOutcome:
    import dlt

    loaded_at = ctx.now

    def make(t: Table) -> Any:
        # Khóa luôn gồm tài khoản nguồn: hai gian hàng của cùng khách ghi chung một bảng mà không đè nhau.
        @dlt.resource(
            name=t.name,
            primary_key=[*t.primary_key, "_dx_source_account"],
            write_disposition="merge",
            max_table_nesting=1,
            columns=dlt_columns(t.schema),
        )
        def res() -> Iterator[dict[str, Any]]:
            st = dlt.current.source_state().setdefault(account, {})
            for r in t.rows(st):
                yield with_contract(r, account, loaded_at)

        return res

    @dlt.source(name=source_name, max_table_nesting=1)
    def src() -> list[Any]:
        return [make(t) for t in tables]

    pipelines_dir = ctx.extra.get("dlt_dir") or os.environ.get("DX_DLT_DIR") or str(Path(".local") / "dlt")
    pipe = dlt.pipeline(
        pipeline_name=pipeline_name.replace("-", "_"),
        destination=_destination(ctx),
        dataset_name=dataset,
        pipelines_dir=str(pipelines_dir),
    )
    try:
        pipe.run(src())
    except Exception as exc:  # dlt bọc lỗi của resource trong PipelineStepFailed
        se = _source_error(exc)
        if se is not None:
            raise se from None
        raise SourceError("api_error", f"dlt: {type(exc).__name__}") from exc
    # Bảng chưa có dữ liệu lần nào vẫn phải tồn tại để dbt đọc được (hợp đồng raw, spec 01 §1).
    existing = set(ctx.warehouse.list_tables(dataset))
    for t in tables:
        if t.name not in existing:
            ctx.warehouse.write_rows(dataset, t.name, {**t.schema, **CONTRACT_SCHEMA}, [])
    counts = pipe.last_trace.last_normalize_info.row_counts if pipe.last_trace.last_normalize_info else {}
    names = {t.name for t in tables}
    tables_out = {k: int(v) for k, v in counts.items() if k in names}
    return SyncOutcome(rows_loaded=sum(tables_out.values()), tables=tables_out)


def open_orders(
    ctx: SyncContext, table: str, key: str, status_col: str, created_col: str, final: set[str], account: str
) -> list[str]:
    """Đơn tạo trong 30 ngày gần nhất chưa ở trạng thái cuối, đọc từ raw (FR-ING-07). Bảng chưa có → rỗng."""
    if table not in ctx.warehouse.list_tables(ctx.raw_dataset):
        return []
    since = int((ctx.now - timedelta(days=RESCAN_DAYS)).timestamp())
    q = '"' if ctx.warehouse.kind == "duckdb" else "`"
    fq = f"{q}{ctx.raw_dataset}{q}.{q}{table}{q}"
    rows = ctx.warehouse.query(
        f"select {key}, {status_col} from (select {key}, {status_col}, row_number() over "
        f"(partition by {key} order by _dx_loaded_at desc) as rn from {fq} "
        f"where cast({created_col} as bigint) >= {since} and _dx_source_account = '{account}') as x where rn = 1"
    )
    return sorted(str(k) for k, s in rows if str(s).upper() not in final)
