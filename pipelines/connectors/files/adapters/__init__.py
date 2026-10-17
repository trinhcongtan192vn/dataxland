"""Adapter theo loại file (spec 07 §4.1). Mỗi adapter chỉ giữ cột cho phép; tên, số điện thoại, địa chỉ, email
người mua bị bỏ trước khi ghi raw; mã người mua nếu có được băm bằng muối của lượt kiểm tra (NFR-03).

Đầu ra: `{tên bảng raw: [bản ghi]}` theo các schema ở `schemas.py`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from connectors.files.adapters import ads, lazada, product_costs, shopee, tiktok_shop

Adapter = Callable[[list[dict[str, Any]], str], dict[str, list[dict[str, Any]]]]

ADAPTERS: dict[str, tuple[str, Adapter]] = {
    "shopee_orders": ("shopee_file", shopee.orders),
    "shopee_income": ("shopee_file", shopee.income),
    "tiktok_shop_orders": ("tiktok_shop_file", tiktok_shop.orders),
    "tiktok_shop_settlement": ("tiktok_shop_file", tiktok_shop.settlement),
    "lazada_orders": ("lazada_file", lazada.orders),
    "lazada_transactions": ("lazada_file", lazada.transactions),
    "meta_ads": ("meta_ads_file", ads.meta),
    "tiktok_ads": ("tiktok_ads_file", ads.tiktok),
    "google_ads": ("google_ads_file", ads.google),
    "product_costs": ("portal_file", product_costs.costs),
}
