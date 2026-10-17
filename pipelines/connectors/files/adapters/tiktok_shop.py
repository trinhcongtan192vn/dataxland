"""TikTok Shop: file xuất đơn và báo cáo quyết toán (spec 07 §4.1)."""

from __future__ import annotations

from typing import Any

from connectors.files.adapters.common import buyer_hash, fee_record, line_record, order_record, return_record, rows
from connectors.files.readers import to_date, to_int, to_num, to_text, to_utc

FEES = {
    "platform_commission": ("Platform commission fee", "Phí hoa hồng nền tảng"),
    "transaction_fee": ("Transaction fee", "Phí giao dịch"),
    "shipping_cost": ("Shipping cost", "Chi phí vận chuyển"),
    "affiliate_commission": ("Affiliate Commission", "Hoa hồng liên kết"),
}


def orders(data: list[dict[str, Any]], salt: str) -> dict[str, list[dict[str, Any]]]:
    """Một dòng mỗi SKU của đơn; giảm giá là tổng của dòng. Bỏ người nhận, điện thoại, địa chỉ; email được băm."""
    out_o: dict[str, dict[str, Any]] = {}
    out_l: list[dict[str, Any]] = []
    out_r: list[dict[str, Any]] = []
    seq: dict[str, int] = {}
    for r in rows(data):
        oid = to_text(r.get("Order ID", "Mã đơn hàng"))
        if not oid:
            continue
        if oid not in out_o:
            out_o[oid] = order_record(
                oid,
                to_utc(r.get("Created Time", "Thời gian tạo")),
                to_text(r.get("Order Status", "Trạng thái đơn hàng")),
                buyer_ref_hash=buyer_hash(salt, r.get("Buyer Email", "Buyer Username")),
            )
        n = seq[oid] = seq.get(oid, 0) + 1
        out_l.append(
            line_record(
                f"{oid}-{n}",
                oid,
                to_text(r.get("Seller SKU", "SKU người bán")),
                to_text(r.get("Product Name", "Tên sản phẩm")),
                to_int(r.get("Quantity", "Số lượng")) or 0,
                to_num(r.get("SKU Unit Original Price", "Giá gốc đơn vị SKU")) or 0,
                to_num(r.get("SKU Seller Discount", "Giảm giá của người bán")),
                to_num(r.get("SKU Platform Discount", "Giảm giá của nền tảng")),
            )
        )
        refund = to_num(r.get("SKU Refund Amount", "Số tiền hoàn lại"))
        if refund:
            out_r.append(
                return_record(
                    f"{oid}-{n}",
                    oid,
                    to_utc(r.get("Refund Time", "Thời gian hoàn tiền")) or out_o[oid]["ordered_at"],
                    refund,
                    to_num(r.get("Return Shipping Fee", "Phí vận chuyển trả hàng")),
                )
            )
    return {
        "tiktok_shop_file__orders": list(out_o.values()),
        "tiktok_shop_file__order_lines": out_l,
        "tiktok_shop_file__returns": out_r,
    }


def settlement(data: list[dict[str, Any]], salt: str) -> dict[str, list[dict[str, Any]]]:
    out: list[dict[str, Any]] = []
    for r in rows(data):
        oid = to_text(r.get("Order/adjustment ID", "Mã đơn hàng/điều chỉnh"))
        if not oid:
            continue
        d = to_date(r.get("Order settled time", "Thời gian quyết toán"))
        for code, names in FEES.items():
            v = to_num(r.get(*names))
            if v:
                out.append(fee_record(oid, d, code, abs(v)))
    return {"tiktok_shop_file__fees": out}
