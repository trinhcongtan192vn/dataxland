"""Báo cáo quảng cáo theo ngày × chiến dịch × nhóm (Meta, TikTok, Google; spec 07 §4.1)."""

from __future__ import annotations

from typing import Any

from connectors.files.adapters.common import rows
from connectors.files.readers import to_date, to_int, to_num, to_text


def _ads(data: list[dict[str, Any]], table: str, cols: dict[str, tuple[str, ...]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[tuple[Any, ...], dict[str, Any]] = {}
    for r in rows(data):
        d = to_date(r.get(*cols["date"]))
        cid = to_text(r.get(*cols["campaign_id"])) or to_text(r.get(*cols["campaign_name"]))
        if d is None or not cid:
            continue
        aid = to_text(r.get(*cols["adgroup_id"])) or to_text(r.get(*cols["adgroup_name"])) or ""
        key = (d, cid, aid)
        rec = out.setdefault(
            key,
            {
                "date": d,
                "campaign_id": cid,
                "campaign_name": to_text(r.get(*cols["campaign_name"])),
                "adgroup_id": aid,
                "adgroup_name": to_text(r.get(*cols["adgroup_name"])),
                "currency": "VND",
                "spend": 0,
                "impressions": 0,
                "clicks": 0,
                "conversions": 0,
                "conversion_value": 0,
            },
        )
        # Một khóa có nhiều dòng (file chia theo quảng cáo): cộng dồn.
        rec["spend"] += to_num(r.get(*cols["spend"])) or 0
        rec["impressions"] += to_int(r.get(*cols["impressions"])) or 0
        rec["clicks"] += to_int(r.get(*cols["clicks"])) or 0
        rec["conversions"] += to_num(r.get(*cols["conversions"])) or 0
        rec["conversion_value"] += to_num(r.get(*cols["conversion_value"])) or 0
    return {table: list(out.values())}


def meta(data: list[dict[str, Any]], salt: str) -> dict[str, list[dict[str, Any]]]:
    return _ads(
        data,
        "meta_ads_file__ad_insights_daily",
        {
            "date": ("Day", "Ngày"),
            "campaign_id": ("Campaign ID", "ID chiến dịch"),
            "campaign_name": ("Campaign name", "Tên chiến dịch"),
            "adgroup_id": ("Ad set ID", "ID nhóm quảng cáo"),
            "adgroup_name": ("Ad set name", "Tên nhóm quảng cáo"),
            "spend": ("Amount spent (VND)", "Số tiền đã chi tiêu (VND)"),
            "impressions": ("Impressions", "Lượt hiển thị"),
            "clicks": ("Link clicks", "Lượt click vào liên kết"),
            "conversions": ("Results", "Kết quả"),
            "conversion_value": ("Purchases conversion value", "Giá trị chuyển đổi mua hàng"),
        },
    )


def tiktok(data: list[dict[str, Any]], salt: str) -> dict[str, list[dict[str, Any]]]:
    return _ads(
        data,
        "tiktok_ads_file__ad_insights_daily",
        {
            "date": ("Date", "Ngày"),
            "campaign_id": ("Campaign ID", "ID chiến dịch"),
            "campaign_name": ("Campaign name", "Tên chiến dịch"),
            "adgroup_id": ("Ad group ID", "ID nhóm quảng cáo"),
            "adgroup_name": ("Ad group name", "Tên nhóm quảng cáo"),
            "spend": ("Cost", "Chi phí"),
            "impressions": ("Impressions", "Lượt hiển thị"),
            "clicks": ("Clicks", "Lượt nhấp"),
            "conversions": ("Conversions", "Chuyển đổi"),
            "conversion_value": ("Total purchase value", "Tổng giá trị mua hàng"),
        },
    )


def google(data: list[dict[str, Any]], salt: str) -> dict[str, list[dict[str, Any]]]:
    return _ads(
        data,
        "google_ads_file__ad_insights_daily",
        {
            "date": ("Day", "Ngày"),
            "campaign_id": ("Campaign ID", "ID chiến dịch"),
            "campaign_name": ("Campaign", "Chiến dịch"),
            "adgroup_id": ("Ad group ID", "ID nhóm quảng cáo"),
            "adgroup_name": ("Ad group", "Nhóm quảng cáo"),
            "spend": ("Cost", "Chi phí"),
            "impressions": ("Impr.", "Lượt hiển thị"),
            "clicks": ("Clicks", "Lượt nhấp"),
            "conversions": ("Conversions", "Lượt chuyển đổi"),
            "conversion_value": ("Conv. value", "Giá trị chuyển đổi"),
        },
    )
