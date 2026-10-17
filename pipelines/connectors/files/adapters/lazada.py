"""Lazada: file xuất đơn (mỗi dòng một sản phẩm) và báo cáo giao dịch (spec 07 §4.1)."""

from __future__ import annotations

from typing import Any

from connectors.files.adapters.common import line_record, order_record, return_record, rows
from connectors.files.readers import to_date, to_num, to_text, to_utc


def orders(data: list[dict[str, Any]], salt: str) -> dict[str, list[dict[str, Any]]]:
    """Giảm giá của shop: `Seller Discount Total`; phần còn lại giữa đơn giá và giá đã trả là của sàn.
    Bỏ tên khách, điện thoại, địa chỉ."""
    out_o: dict[str, dict[str, Any]] = {}
    out_l: list[dict[str, Any]] = []
    out_r: list[dict[str, Any]] = []
    for r in rows(data):
        oid = to_text(r.get("Order Number", "Mã đơn hàng"))
        item = to_text(r.get("Order Item Id", "Mã sản phẩm đơn hàng"))
        if not oid or not item:
            continue
        if oid not in out_o:
            out_o[oid] = order_record(
                oid, to_utc(r.get("Created at", "Ngày tạo")), to_text(r.get("Status", "Trạng thái"))
            )
        unit = to_num(r.get("Unit Price", "Đơn giá")) or 0
        paid = to_num(r.get("Paid Price", "Giá đã trả"))
        seller = to_num(r.get("Seller Discount Total", "Tổng giảm giá của người bán")) or 0
        platform = max(unit - paid - seller, 0) if paid is not None else 0
        out_l.append(
            line_record(
                item,
                oid,
                to_text(r.get("Seller SKU", "SKU người bán")),
                to_text(r.get("Item Name", "Tên sản phẩm")),
                1,
                unit,
                seller,
                platform,
            )
        )
        refund = to_num(r.get("Refund Amount", "Số tiền hoàn lại"))
        if refund:
            out_r.append(
                return_record(
                    item, oid, to_utc(r.get("Refund Date", "Ngày hoàn tiền")) or out_o[oid]["ordered_at"], refund
                )
            )
    return {
        "lazada_file__orders": list(out_o.values()),
        "lazada_file__order_lines": out_l,
        "lazada_file__returns": out_r,
    }


def transactions(data: list[dict[str, Any]], salt: str) -> dict[str, list[dict[str, Any]]]:
    """Số âm là tiền người bán trả; đổi thành số dương. Tên phí giữ nguyên để ánh xạ bằng `fee_type_map__lazada`."""
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows(data), start=1):
        oid = to_text(r.get("Order No.", "Mã đơn hàng"))
        fee = to_text(r.get("Fee Name", "Tên phí"))
        amount = to_num(r.get("Amount", "Số tiền"))
        if not oid or not fee or amount is None:
            continue
        out.append(
            {
                "fee_id": f"{oid}-{i}",
                "order_id": oid,
                "fee_date": to_date(r.get("Transaction Date", "Ngày giao dịch")),
                "fee_type_raw": fee,
                "amount": -amount,
                "currency": "VND",
            }
        )
    return {"lazada_file__fees": out}
