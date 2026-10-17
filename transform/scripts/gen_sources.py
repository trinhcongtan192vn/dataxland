"""Sinh `models/sources.yml`: bảng raw theo hợp đồng nạp (spec 01 §1), bật theo biến `sources`, độ tươi theo
`freshness_hours` (FR-DQ-01). Chạy: `uv run python transform/scripts/gen_sources.py`.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "models"
TABLES = {
    "shopee": ["orders", "order_items", "escrow", "returns", "products", "daily_totals"],
    "tiktok_shop": ["orders", "order_items", "settlements", "returns", "products", "daily_totals"],
    "lazada": ["orders", "order_items", "transactions", "returns", "products", "daily_totals"],
    "amazon_seller": ["orders", "order_items", "financial_events", "daily_totals"],
    "meta_ads": ["ad_insights_daily"],
    "tiktok_ads": ["ad_insights_daily"],
    "google_ads": ["ad_insights_daily"],
    "amazon_ads": ["ad_insights_daily"],
    "portal": ["product_costs", "ad_budgets"],
    "shopee_file": ["orders", "order_lines", "fees", "returns"],
    "tiktok_shop_file": ["orders", "order_lines", "fees", "returns"],
    "lazada_file": ["orders", "order_lines", "fees", "returns"],
    "meta_ads_file": ["ad_insights_daily"],
    "tiktok_ads_file": ["ad_insights_daily"],
    "google_ads_file": ["ad_insights_daily"],
    "portal_file": ["product_costs"],
}
NO_FRESHNESS = {"portal", "daily_totals", "products"}


def main() -> None:
    lines = [
        "# Tự sinh bởi transform/scripts/gen_sources.py – sửa ở đó, không sửa tay.",
        "version: 2",
        "",
        "sources:",
        "  - name: raw",
        "    schema: \"{{ var('dataset_prefix') }}_raw\"",
        "    loaded_at_field: _dx_loaded_at",
        "    tables:",
        "      - name: dx__status_map_override",
        "        description: Ghi đè ánh xạ trạng thái theo khách, Dagster nạp trước dbt build (spec 02 §3.3).",
    ]
    for src, objs in TABLES.items():
        for obj in objs:
            lines.append(f"      - name: {src}__{obj}")
            lines.append("        config:")
            lines.append(f"          enabled: \"{{{{ '{src}' in var('sources', []) }}}}\"")
            fresh = not (src in NO_FRESHNESS or obj in NO_FRESHNESS or src.endswith("_file"))
            if fresh:
                lines.append("          tags: [freshness]")
                lines.append("          freshness:")
                lines.append("            error_after: {count: \"{{ var('freshness_hours') | int }}\", period: hour}")
            else:
                lines.append("          freshness: null")
    lines += [
        "  - name: identity",
        "    schema: \"{{ var('dataset_prefix') }}_core\"",
        "    tables:",
        "      - name: identity_map",
        "        description: Cặp ghép đã duyệt từ S3 (spec 10 §6); Dagster tạo bảng trống nếu chưa có.",
        "  - name: dx_ref",
        "    schema: dx_ref",
        "    tables:",
        "      - name: fx_rates",
        "        description: Tỷ giá Vietcombank và tỷ giá nhập tay (spec 01 §6).",
        "",
    ]
    (ROOT / "sources.yml").write_bytes("\n".join(lines).encode("utf-8"))
    print("ok")


if __name__ == "__main__":
    main()
