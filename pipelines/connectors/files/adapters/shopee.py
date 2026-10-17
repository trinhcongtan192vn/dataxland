"""Shopee: file xuất đơn hàng và báo cáo doanh thu (spec 07 §4.1)."""

from __future__ import annotations

from typing import Any

from connectors.files.adapters.common import buyer_hash, fee_record, line_record, order_record, return_record, rows
from connectors.files.readers import to_date, to_int, to_num, to_text, to_utc


def orders(data: list[dict[str, Any]], salt: str) -> dict[str, list[dict[str, Any]]]:
    """Mỗi dòng là một dòng đơn; cột cấp đơn (voucher) lặp lại theo dòng. Bỏ người nhận, điện thoại, địa chỉ."""
    out_o: dict[str, dict[str, Any]] = {}
    out_l: list[dict[str, Any]] = []
    out_r: list[dict[str, Any]] = []
    seq: dict[str, int] = {}
    for r in rows(data):
        oid = to_text(r.get("Mã đơn hàng", "Order ID"))
        if not oid:
            continue
        if oid not in out_o:
            out_o[oid] = order_record(
                oid,
                to_utc(r.get("Ngày đặt hàng", "Order Creation Date")),
                to_text(r.get("Trạng Thái Đơn Hàng", "Trạng thái đơn hàng", "Order Status")),
                seller_discount=to_num(r.get("Mã giảm giá của Shop", "Seller Voucher")),
                platform_discount=to_num(r.get("Mã giảm giá của Shopee", "Shopee Voucher")),
                buyer_ref_hash=buyer_hash(salt, r.get("Người Mua", "Username (Buyer)")),
            )
        n = seq[oid] = seq.get(oid, 0) + 1
        qty = to_int(r.get("Số lượng", "Quantity")) or 0
        orig = to_num(r.get("Giá gốc", "Original Price")) or 0
        deal = to_num(r.get("Giá ưu đãi", "Deal Price"))
        disc = (orig - deal) * qty if deal is not None else 0
        out_l.append(
            line_record(
                f"{oid}-{n}",
                oid,
                to_text(r.get("SKU phân loại hàng", "SKU Reference No.", "Variation SKU")),
                to_text(r.get("Tên sản phẩm", "Product Name")),
                qty,
                orig,
                disc,
            )
        )
        refund = to_num(r.get("Số tiền hoàn lại", "Refund Amount"))
        if refund:
            out_r.append(
                return_record(
                    f"{oid}-{n}",
                    oid,
                    to_utc(r.get("Ngày trả hàng/hoàn tiền", "Return Date")) or out_o[oid]["ordered_at"],
                    refund,
                    to_num(r.get("Phí vận chuyển trả hàng", "Return Shipping Fee")),
                )
            )
    return {
        "shopee_file__orders": list(out_o.values()),
        "shopee_file__order_lines": out_l,
        "shopee_file__returns": out_r,
    }


def income(data: list[dict[str, Any]], salt: str) -> dict[str, list[dict[str, Any]]]:
    """Phí theo đơn từ báo cáo doanh thu, quy về cùng mã phí với API (`fee_type_map__shopee`)."""
    out: list[dict[str, Any]] = []
    for r in rows(data):
        oid = to_text(r.get("Mã đơn hàng", "Order ID"))
        if not oid:
            continue
        d = to_date(r.get("Ngày hoàn thành thanh toán", "Payout Completed Date"))
        fees = {
            "commission_fee": to_num(r.get("Phí cố định", "Commission Fee")),
            "service_fee": to_num(r.get("Phí Dịch Vụ", "Phí dịch vụ", "Service Fee")),
            "seller_transaction_fee": to_num(r.get("Phí thanh toán", "Transaction Fee")),
            "net_shipping_fee": (to_num(r.get("Phí vận chuyển thực tế", "Actual Shipping Fee")) or 0)
            - (to_num(r.get("Phí vận chuyển được trợ giá từ Shopee", "Shopee Shipping Rebate")) or 0)
            - (to_num(r.get("Phí vận chuyển Người mua trả", "Shipping Fee Paid by Buyer")) or 0),
        }
        for k, v in fees.items():
            if v:
                out.append(fee_record(oid, d, k, abs(v) if k != "net_shipping_fee" else v))
    return {"shopee_file__fees": out}
