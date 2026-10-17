"""Connector J&T Express qua file đối soát (FR-ING-09, ADR 0005).

Khách tải file đối soát (xlsx, csv) ở cổng; API lưu file vào `METADATA_BUCKET/carrier-files/<khách>/` và ghi
`carrier_files` (`received`). Mỗi lần chạy, connector đọc các file mới, nhận diện mẫu `jnt_reconcile`
(`connectors/files/signatures.yml`), ghi `merge` vào `jnt__shipments` theo mã vận đơn rồi đánh dấu file `loaded` hoặc
`rejected`. Cột người nhận trong file không được đọc.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from connectors.base import SyncContext, SyncOutcome
from connectors.carriers.common import SHIPMENTS
from connectors.common.load import Table, run_tables
from connectors.files import readers
from connectors.files.source import read_bytes
from dx_common.db import get_engine
from dx_common.tenants import SourceConfig, TenantConfig

KIND = "jnt_reconcile"


def parse_file(raw: bytes, filename: str) -> tuple[list[dict[str, Any]], str | None]:
    """Trả (dòng vận đơn, lỗi tiếng Việt nếu file không dùng được)."""
    try:
        table = readers.read_table(raw, filename)
    except readers.FileError as exc:
        return [], exc.message_vi
    sc, missing = readers.score(KIND, table.headers)
    if sc < readers.MATCH_RATIO:
        return [], f"File không đúng mẫu đối soát J&T. Thiếu các cột: {', '.join(missing)}"
    out: dict[str, dict[str, Any]] = {}
    for d in table.rows:
        r = readers.Row(d)
        waybill = readers.to_text(r.get("Mã vận đơn", "Waybill No", "Billcode"))
        if not waybill:
            continue
        sent = readers.to_utc(r.get("Ngày gửi", "Ngày gửi hàng", "Ship Date", "Pickup Time"))
        done = readers.to_utc(r.get("Ngày cập nhật", "Ngày ký nhận", "Update Time", "Sign Time"))
        out[waybill] = {
            "waybill": waybill,
            "client_order_code": readers.to_text(r.get("Mã đơn hàng", "Order No", "Mã đơn khách hàng")),
            "status_raw": readers.to_text(r.get("Trạng thái", "Status")),
            "created_at": sent,
            "updated_at": done or sent,
            "shipping_fee": readers.to_num(r.get("Phí vận chuyển", "Freight", "Cước phí")),
            "cod_amount": readers.to_num(r.get("Tiền COD", "COD Amount", "Tiền thu hộ")),
            "return_fee": readers.to_num(r.get("Phí hoàn", "Return Fee", "Phí chuyển hoàn")),
            "insurance_fee": readers.to_num(r.get("Phí bảo hiểm", "Insurance Fee")),
            "weight_g": _grams(r.get("Trọng lượng (kg)", "Trọng lượng", "Weight (kg)")),
        }
    return list(out.values()), None


def _grams(v: Any) -> int | None:
    kg = readers.to_num(v)
    return None if kg is None else int(kg * 1000)


def _pending(tenant_id: str) -> list[dict[str, Any]]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "select id, filename, storage_path from carrier_files where tenant_id = :t and carrier = 'jnt' "
                "and status = 'received' order by created_at"
            ),
            {"t": tenant_id},
        ).mappings()
        return [dict(r) for r in rows]


def _mark(file_id: str, status: str, rows: int | None, error: str | None) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "update carrier_files set status = :s, rows_loaded = :n, error_message_vi = :e, updated_at = now() "
                "where id = :id"
            ),
            {"s": status, "n": rows, "e": error, "id": file_id},
        )


def sync_jnt(tenant: TenantConfig, source: SourceConfig, ctx: SyncContext) -> SyncOutcome:
    files = ctx.extra.get("jnt_files")
    pending = files if files is not None else _pending(tenant.tenant_id)
    merged: dict[str, dict[str, Any]] = {}
    marks: list[tuple[str, str, int | None, str | None]] = []
    for f in pending:
        raw = f["content"] if "content" in f else read_bytes(f["storage_path"])
        rows, err = parse_file(raw, f["filename"])
        if err:
            marks.append((f["id"], "rejected", None, err))
            continue
        for r in rows:
            merged[r["waybill"]] = r
        marks.append((f["id"], "loaded", len(rows), None))
    out = run_tables(
        tenant, source, ctx, [Table("jnt__shipments", ["waybill"], lambda st: list(merged.values()), SHIPMENTS)]
    )
    if files is None:
        for m in marks:
            _mark(*m)
    out.note = f"{len(marks)} file"
    return out
