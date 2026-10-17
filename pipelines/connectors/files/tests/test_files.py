"""Adapter file kiểm tra sức khỏe (spec 07 §4, §10): FR-HC-01, NFR-03."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from connectors.files import readers
from connectors.files.source import process_file

SAMPLES = Path(__file__).resolve().parents[4] / "transform" / "samples" / "files"
KINDS = {
    "shopee_orders.xlsx": "shopee_orders",
    "shopee_income.xlsx": "shopee_income",
    "tiktok_shop_orders.csv": "tiktok_shop_orders",
    "tiktok_shop_settlement.csv": "tiktok_shop_settlement",
    "lazada_orders.xlsx": "lazada_orders",
    "lazada_transactions.csv": "lazada_transactions",
    "meta_ads.csv": "meta_ads",
    "tiktok_ads.csv": "tiktok_ads",
    "google_ads.csv": "google_ads",
    "product_costs.xlsx": "product_costs",
}


@pytest.mark.parametrize(("name", "kind"), list(KINDS.items()))
def test_every_sample_detected_and_loaded(name: str, kind: str) -> None:
    st, out = process_file((SAMPLES / name).read_bytes(), name, kind, "salt")
    assert st["status"] == "loaded", st
    assert st["detected_kind"] == kind and st["rows_loaded"] > 0


def test_fr_hc_01_detect_wrong_file() -> None:
    st, out = process_file((SAMPLES / "lazada_orders.xlsx").read_bytes(), "lazada_orders.xlsx", "shopee_orders", "s")
    assert st["status"] == "rejected" and out == {}
    assert st["error_message_vi"] == "File này giống Đơn hàng Lazada, không phải Đơn hàng Shopee"


def test_unrecognized_file_lists_missing_columns() -> None:
    raw = "Mã đơn hàng,Cột lạ\n123,abc\n".encode("utf-8-sig")
    st, _ = process_file(raw, "x.csv", "shopee_orders", "s")
    assert st["error_code"] == "NOT_RECOGNIZED"
    assert st["error_message_vi"].startswith("File không đúng mẫu Đơn hàng Shopee. Thiếu các cột:")
    assert "Ngày đặt hàng" in st["error_message_vi"]


def test_nfr_03_pii_not_in_output() -> None:
    for name, kind in [
        ("shopee_orders.xlsx", "shopee_orders"),
        ("tiktok_shop_orders.csv", "tiktok_shop_orders"),
        ("lazada_orders.xlsx", "lazada_orders"),
    ]:
        _, out = process_file((SAMPLES / name).read_bytes(), name, kind, "salt")
        text = repr(out)
        assert "0909861532" not in text and "Vũ Bình" not in text and "@mail.example" not in text
        for recs in out.values():
            for r in recs:
                assert not {"recipient_name", "recipient_phone", "address", "buyer_email"} & set(r)


def test_csv_encodings_and_delimiters() -> None:
    header = "Day;Campaign;Campaign ID;Ad group;Ad group ID;Cost;Impr.;Clicks;Conversions;Conv. value\n"
    row = "2026-10-01;Chiến dịch A;c1;Nhóm 1;g1;1.234.567;1000;10;2;5.000.000\n"
    raw = (header + row).encode("utf-16")
    st, out = process_file(raw, "google.csv", "google_ads", "s")
    assert st["status"] == "loaded", st
    rec = out["google_ads_file__ad_insights_daily"][0]
    assert rec["spend"] == 1234567 and rec["conversion_value"] == 5000000


def test_to_num_formats() -> None:
    assert readers.to_num("120.000") == 120000
    assert readers.to_num("120,000") == 120000
    assert readers.to_num("-35,840.50") == pytest.approx(-35840.5)
    assert readers.to_num("(1.000)") == -1000
    assert readers.to_num("12,5") == pytest.approx(12.5)


def test_xlsx_with_blank_leading_rows() -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([None])
    ws.append(["ma_sku", "gia_von", "ap_dung_tu", "ghi_chu"])
    ws.append(["SKU-1", 1000, "01/10/2026", None])
    buf = io.BytesIO()
    wb.save(buf)
    st, out = process_file(buf.getvalue(), "costs.xlsx", "product_costs", "s")
    assert st["status"] == "loaded"
    assert out["portal_file__product_costs"][0]["valid_from"].isoformat() == "2026-10-01"
