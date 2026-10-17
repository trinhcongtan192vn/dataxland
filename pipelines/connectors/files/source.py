"""Nạp file kiểm tra sức khỏe vào `hc_<check_id>_raw` (spec 07 §4, §5 bước 2).

Mỗi file: đọc → nhận diện loại → so với loại khách chọn → adapter (bỏ thông tin người mua) → gom theo bảng.
File lỗi được đánh dấu `rejected`, các file khác vẫn chạy. Lượt kiểm tra chạy một lần nên mỗi bảng được ghi đè
toàn bộ (cùng hợp đồng raw spec 01 §1, `_dx_source_account = 'file'`).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from connectors.base import with_contract
from connectors.files import readers
from connectors.files.adapters import ADAPTERS
from dx_common.timeutil import now_utc

ORDERS = {
    "order_id": "string",
    "ordered_at": "timestamp",
    "status_raw": "string",
    "currency": "string",
    "order_seller_discount": "numeric",
    "order_platform_discount": "numeric",
    "buyer_ref_hash": "string",
}
LINES = {
    "line_id": "string",
    "order_id": "string",
    "seller_sku": "string",
    "item_name": "string",
    "quantity": "int",
    "unit_original_price": "numeric",
    "line_seller_discount": "numeric",
    "line_platform_discount": "numeric",
}
FEES = {
    "fee_id": "string",
    "order_id": "string",
    "fee_date": "date",
    "fee_type_raw": "string",
    "amount": "numeric",
    "currency": "string",
}
ADS = {
    "date": "date",
    "campaign_id": "string",
    "campaign_name": "string",
    "adgroup_id": "string",
    "adgroup_name": "string",
    "currency": "string",
    "spend": "numeric",
    "impressions": "int",
    "clicks": "int",
    "conversions": "numeric",
    "conversion_value": "numeric",
}
RETURNS = {
    "return_id": "string",
    "order_id": "string",
    "line_id": "string",
    "returned_at": "timestamp",
    "refund_amount": "numeric",
    "return_fee": "numeric",
}
COSTS = {"id": "string", "seller_sku": "string", "unit_cost_vnd": "numeric", "valid_from": "date", "note": "string"}
CONTRACT = {"_dx_loaded_at": "timestamp", "_dx_source_account": "string", "_dx_record_hash": "string"}


def schema_for(table: str) -> dict[str, str]:
    obj = table.split("__", 1)[1]
    base = {
        "orders": ORDERS,
        "order_lines": LINES,
        "fees": FEES,
        "returns": RETURNS,
        "ad_insights_daily": ADS,
        "product_costs": COSTS,
    }[obj]
    return {**base, **CONTRACT}


# Bảng đi theo từng nguồn: một nguồn chỉ bật khi đủ bảng để staging đọc được.
TABLES = {
    "shopee_file": ["shopee_file__orders", "shopee_file__order_lines", "shopee_file__fees", "shopee_file__returns"],
    "tiktok_shop_file": [
        "tiktok_shop_file__orders",
        "tiktok_shop_file__order_lines",
        "tiktok_shop_file__fees",
        "tiktok_shop_file__returns",
    ],
    "lazada_file": ["lazada_file__orders", "lazada_file__order_lines", "lazada_file__fees", "lazada_file__returns"],
    "meta_ads_file": ["meta_ads_file__ad_insights_daily"],
    "tiktok_ads_file": ["tiktok_ads_file__ad_insights_daily"],
    "google_ads_file": ["google_ads_file__ad_insights_daily"],
    "portal_file": ["portal_file__product_costs"],
}
DATE_FIELDS = ("ordered_at", "fee_date", "date", "returned_at")


def read_bytes(path: str) -> bytes:
    if path.startswith("gs://"):  # pragma: no cover - cần GCS
        from google.cloud import storage

        bucket, _, name = path[5:].partition("/")
        return bytes(storage.Client().bucket(bucket).blob(name).download_as_bytes())
    return Path(path).read_bytes()


def process_file(
    raw: bytes, filename: str, declared: str, salt: str
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """Trả (trạng thái file, bảng → bản ghi). Không ném lỗi: file lỗi có `status = rejected`."""
    status: dict[str, Any] = {
        "status": "loaded",
        "detected_kind": None,
        "error_code": None,
        "error_message_vi": None,
        "date_from": None,
        "date_to": None,
        "rows_loaded": 0,
    }
    try:
        table = readers.read_table(raw, filename)
    except readers.FileError as exc:
        return {**status, "status": "rejected", "error_code": exc.code, "error_message_vi": exc.message_vi}, {}
    detected = readers.detect(table.headers)
    status["detected_kind"] = detected
    if detected is None:
        _, missing = readers.score(declared, table.headers)
        return {
            **status,
            "status": "rejected",
            "error_code": "NOT_RECOGNIZED",
            "error_message_vi": f"File không đúng mẫu {readers.label(declared)}. Thiếu các cột: {', '.join(missing)}",
        }, {}
    if detected != declared:
        return {
            **status,
            "status": "rejected",
            "error_code": "WRONG_KIND",
            "error_message_vi": f"File này giống {readers.label(detected)}, không phải {readers.label(declared)}",
        }, {}
    _, adapter = ADAPTERS[declared]
    out = adapter(table.rows, salt)
    dates: list[date] = []
    for recs in out.values():
        for r in recs:
            for f in DATE_FIELDS:
                v = r.get(f)
                if v is not None:
                    dates.append(v.date() if hasattr(v, "date") and callable(v.date) else v)
    n = sum(len(v) for v in out.values())
    if n == 0:
        return {
            **status,
            "status": "rejected",
            "error_code": "NO_ROWS",
            "error_message_vi": "File không có dòng dữ liệu hợp lệ",
        }, {}
    status.update(
        rows_loaded=n,
        date_from=min(dates).isoformat() if dates else None,
        date_to=max(dates).isoformat() if dates else None,
    )
    return status, out


def load_files(
    check_id: str, files: list[dict[str, Any]], salt: str, warehouse: Any, raw_dataset: str
) -> dict[str, Any]:
    """`files`: `[{id, declared_kind, filename, path}]` từ `POST /v1/internal/health-checks/{id}/start`."""
    loaded_at = now_utc()
    tables: dict[str, list[dict[str, Any]]] = defaultdict(list)
    results: list[dict[str, Any]] = []
    ranges: dict[str, dict[str, str | None]] = {}
    for f in files:
        try:
            raw = read_bytes(f["path"])
        except OSError:
            results.append(
                {
                    "id": f["id"],
                    "status": "rejected",
                    "error_code": "MISSING",
                    "error_message_vi": "Không tìm thấy file đã tải lên",
                }
            )
            continue
        st, out = process_file(raw, f["filename"], f["declared_kind"], salt)
        results.append({"id": f["id"], **st})
        if st["status"] != "loaded":
            continue
        ranges[f["id"]] = {"kind": f["declared_kind"], "from": st["date_from"], "to": st["date_to"]}
        for t, recs in out.items():
            tables[t] += [with_contract(r, "file", loaded_at) for r in recs]
    sources = [s for s, ts in TABLES.items() if any(t in tables for t in ts)]
    for s in sources:  # nguồn có file thì mọi bảng của nguồn đều phải tồn tại (có thể rỗng)
        for t in TABLES[s]:
            warehouse.write_rows(raw_dataset, t, schema_for(t), tables.get(t, []))
    return {"files": results, "sources": sources, "ranges": ranges}
