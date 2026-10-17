"""Sinh `models/staging/_staging.yml` từ hợp đồng đầu ra của staging (spec 02 §3.2).

Mọi model staging cùng loại có đủ cột, cùng tên, cùng kiểu, bật `contract: enforced: true`, kèm test:
- `accepted_values` trên `status`, `reason`, `cost_type` (chưa ánh xạ → lỗi, mức chặn; FR-MOD-01);
- `not_null` trên mọi cột `*_vnd` (thiếu tỷ giá → lỗi, mức chặn; FR-MOD-03);
- `unique`, `not_null` trên khóa nguồn.

Chạy: `uv run python transform/scripts/gen_staging_yml.py`
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STATUSES = ["pending", "confirmed", "shipping", "delivered", "completed", "cancelled", "returned", "failed_delivery"]
REASONS = ["buyer_changed_mind", "damaged", "wrong_item", "not_received", "quality", "failed_delivery", "other"]
COST_TYPES = ["platform_fee", "payment_fee", "shipping", "ad_spend", "other"]
SHIP_STATUSES = ["pending", "in_transit", "delivered", "returning", "returned", "cancelled", "failed"]

S, TS, D, N, INT, B = "string", "timestamp", "date", "numeric", "bigint", "boolean"

CONTRACTS: dict[str, list[tuple[str, str]]] = {
    "orders": [
        ("source", S),
        ("source_id", S),
        ("source_account", S),
        ("ordered_at", TS),
        ("updated_at", TS),
        ("order_date", D),
        ("status_raw", S),
        ("status", S),
        ("buyer_ref", S),
        ("buyer_phone_hash", S),
        ("buyer_email_hash", S),
        ("currency", S),
        ("gross_amount_original", N),
        ("discount_amount_original", N),
        ("seller_discount_original", N),
        ("platform_discount_original", N),
        ("gross_amount_vnd", N),
        ("discount_amount_vnd", N),
        ("net_amount_vnd", N),
        ("settled_at", TS),
    ],
    "order_lines": [
        ("source", S),
        ("source_id", S),
        ("order_source_id", S),
        ("seller_sku", S),
        ("item_name", S),
        ("quantity", INT),
        ("unit_price_vnd", N),
        ("line_gross_vnd", N),
        ("allocated_discount_vnd", N),
    ],
    "fees": [
        ("source", S),
        ("source_id", S),
        ("order_source_id", S),
        ("source_account", S),
        ("fee_date", D),
        ("fee_type_raw", S),
        ("cost_type", S),
        ("amount_original", N),
        ("currency", S),
        ("amount_vnd", N),
    ],
    "returns": [
        ("source", S),
        ("source_id", S),
        ("order_source_id", S),
        ("order_line_source_id", S),
        ("returned_at", TS),
        ("return_date", D),
        ("reason_raw", S),
        ("reason", S),
        ("refund_amount_vnd", N),
        ("return_fee_vnd", N),
        ("status", S),
    ],
    "products": [("source", S), ("source_id", S), ("seller_sku", S), ("name", S), ("barcode", S), ("category_raw", S)],
    "ad_insights_daily": [
        ("source", S),
        ("source_account", S),
        ("date", D),
        ("campaign_id", S),
        ("campaign_name", S),
        ("adgroup_id", S),
        ("adgroup_name", S),
        ("currency", S),
        ("spend_original", N),
        ("spend_vnd", N),
        ("impressions", INT),
        ("clicks", INT),
        ("conversions", N),
        ("conversion_value_original", N),
        ("conversion_value_vnd", N),
    ],
    "daily_totals": [("source", S), ("source_account", S), ("date", D), ("order_count", INT), ("gross_amount_vnd", N)],
    # FR-ING-09: vận đơn của hãng vận chuyển, khóa mã vận đơn (spec 01 §9).
    "shipments": [
        ("source", S),
        ("source_id", S),
        ("source_account", S),
        ("order_source_id", S),
        ("status_raw", S),
        ("status", S),
        ("created_at", TS),
        ("updated_at", TS),
        ("ship_date", D),
        ("cod_vnd", N),
        ("shipping_fee_vnd", N),
        ("return_fee_vnd", N),
        ("insurance_fee_vnd", N),
    ],
}

MODELS: dict[str, list[str]] = {
    "shopee": ["orders", "order_lines", "fees", "returns", "products", "daily_totals"],
    "tiktok_shop": ["orders", "order_lines", "fees", "returns", "products", "daily_totals"],
    "lazada": ["orders", "order_lines", "fees", "returns", "products", "daily_totals"],
    "amazon_seller": ["orders", "order_lines", "fees", "returns", "products", "daily_totals"],
    "meta_ads": ["ad_insights_daily"],
    "tiktok_ads": ["ad_insights_daily"],
    "google_ads": ["ad_insights_daily"],
    "amazon_ads": ["ad_insights_daily"],
    "shopee_file": ["orders", "order_lines", "fees", "returns", "products"],
    "tiktok_shop_file": ["orders", "order_lines", "fees", "returns", "products"],
    "lazada_file": ["orders", "order_lines", "fees", "returns", "products"],
    "meta_ads_file": ["ad_insights_daily"],
    "tiktok_ads_file": ["ad_insights_daily"],
    "google_ads_file": ["ad_insights_daily"],
    "ghn": ["shipments"],
    "ghtk": ["shipments"],
    "jnt": ["shipments"],
}
KEYS = {
    "daily_totals": ["source_account", "date"],
    "ad_insights_daily": ["source_account", "date", "campaign_id", "adgroup_id"],
}
OPTIONAL_VND = {"settled_at"}


def model_yaml(source: str, obj: str) -> list[str]:
    name = f"stg_{source}__{obj}"
    out = [f"  - name: {name}", "    config:", "      contract: {enforced: true}", "    columns:"]
    for col, typ in CONTRACTS[obj]:
        tests: list[str] = []
        if col == "source_id" and obj not in KEYS:
            tests += ["unique", "not_null"]
        if col.endswith("_vnd"):
            tests.append("not_null")
        if col in ("source", "date", "order_date", "fee_date", "return_date") or (
            col == "order_source_id" and obj not in ("fees", "shipments")
        ):
            tests.append("not_null")
        line = f"      - name: {col}\n        data_type: {typ}"
        if col == "status" and obj == "orders":
            line += (
                "\n        data_tests:\n          - not_null\n          - accepted_values:\n              arguments:\n"
                f"                values: {STATUSES}\n              config: {{severity: error}}"
            )
            out.append(line)
            continue
        if col == "status" and obj == "shipments":
            line += (
                "\n        data_tests:\n          - not_null\n          - accepted_values:\n              arguments:\n"
                f"                values: {SHIP_STATUSES}\n              config: {{severity: error}}"
            )
            out.append(line)
            continue
        if col == "reason":
            line += (
                "\n        data_tests:\n          - not_null\n          - accepted_values:\n              arguments:\n"
                f"                values: {REASONS}"
            )
            out.append(line)
            continue
        if col == "cost_type":
            line += (
                "\n        data_tests:\n          - not_null\n          - accepted_values:\n              arguments:\n"
                f"                values: {COST_TYPES}"
            )
            out.append(line)
            continue
        if tests:
            line += "\n        data_tests: [" + ", ".join(dict.fromkeys(tests)) + "]"
        out.append(line)
    if obj in KEYS:
        out += [
            "    data_tests:",
            "      - dbt_utils.unique_combination_of_columns:",
            "          arguments:",
            f"            combination_of_columns: {KEYS[obj]}",
        ]
    return out


def main() -> None:
    lines = [
        "# Tự sinh bởi transform/scripts/gen_staging_yml.py từ hợp đồng spec 02 §3.2 – sửa ở script, không sửa tay.",
        "version: 2",
        "",
        "models:",
        "  - name: stg_fx__rates_daily",
        "    description: Tỷ giá theo ngày đã điền ngày trống (spec 02 §3.2).",
        "    config:",
        "      contract: {enforced: true}",
        "    columns:",
        "      - {name: date, data_type: date, data_tests: [not_null]}",
        "      - {name: currency, data_type: string, data_tests: [not_null]}",
        "      - {name: rate_vnd, data_type: numeric, data_tests: [not_null]}",
        "    data_tests:",
        "      - dbt_utils.unique_combination_of_columns:",
        "          arguments:",
        "            combination_of_columns: [date, currency]",
        "  - name: stg_portal__product_costs",
        "    config:",
        "      contract: {enforced: true}",
        "    columns:",
        "      - {name: source_id, data_type: string, data_tests: [not_null, unique]}",
        "      - {name: seller_sku, data_type: string, data_tests: [not_null]}",
        "      - {name: unit_cost_vnd, data_type: numeric, data_tests: [not_null]}",
        "      - {name: valid_from, data_type: date, data_tests: [not_null]}",
        "      - {name: deleted, data_type: boolean}",
        "  - name: stg_portal__ad_budgets",
        "    config:",
        "      contract: {enforced: true}",
        "    columns:",
        "      - {name: source_id, data_type: string, data_tests: [not_null, unique]}",
        "      - {name: platform, data_type: string, data_tests: [not_null]}",
        "      - {name: month, data_type: date, data_tests: [not_null]}",
        "      - {name: campaign_id, data_type: string}",
        "      - {name: budget_vnd, data_type: numeric, data_tests: [not_null]}",
        "      - {name: deleted, data_type: boolean}",
        "  - name: stg_portal_file__product_costs",
        "    config:",
        "      contract: {enforced: true}",
        "    columns:",
        "      - {name: source_id, data_type: string, data_tests: [not_null, unique]}",
        "      - {name: seller_sku, data_type: string, data_tests: [not_null]}",
        "      - {name: unit_cost_vnd, data_type: numeric, data_tests: [not_null]}",
        "      - {name: valid_from, data_type: date, data_tests: [not_null]}",
        "      - {name: deleted, data_type: boolean}",
    ]
    for source, objs in MODELS.items():
        for obj in objs:
            lines += model_yaml(source, obj)
    (ROOT / "models" / "staging" / "_staging.yml").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    write_contract_macro()
    print("ok")


TYPE_MACRO = {
    S: "dbt.type_string()",
    TS: "dbt.type_timestamp()",
    D: "'date'",
    N: "'numeric'",
    INT: "dbt.type_bigint()",
    B: "dbt.type_boolean()",
}


def write_contract_macro() -> None:
    """`dx_contract(object)` trả {cột: kiểu} của hợp đồng staging, dùng trong `dx_union_enabled`."""
    out = [
        "{#- Tự sinh bởi transform/scripts/gen_staging_yml.py – không sửa tay. -#}",
        "{% macro dx_contract(object) -%}",
        "    {%- set c = {",
    ]
    for obj, cols in CONTRACTS.items():
        inner = ", ".join(f"'{c}': {TYPE_MACRO[t]}" for c, t in cols)
        out.append(f"        '{obj}': {{{inner}}},")
    out += ["    } -%}", "    {{ return(c[object]) }}", "{%- endmacro %}", ""]
    (ROOT / "macros" / "dx_contracts.sql").write_bytes("\n".join(out).encode("utf-8"))


if __name__ == "__main__":
    main()
