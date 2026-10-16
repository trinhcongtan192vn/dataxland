# Implementation Plan: Biến đổi và chất lượng dữ liệu

**Branch**: `004-dbt-transform` | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

## Technical Context

dbt-core 1.10, dbt-duckdb, dbt-bigquery, dbt_utils 1.3.0, elementary 0.21.0 (chỉ BigQuery, ADR 0003).

## Constitution Check

| Nguyên tắc | Kết quả |
|---|---|
| I | Cột, khóa, test theo 02; chiều `sku`, `product_name` và `int_*` ghi ở ADR 0002 #18; Elementary trên DuckDB: ADR 0003 (Proposed) |
| II | Mọi dataset qua `var('dataset_prefix')`; test `test_isolation_no_cross_tenant_reference` quét manifest |
| III | Marts chỉ chứa cột cộng được; công thức chỉ số nằm ở lớp chỉ số (feature 005) |
| IV | Staging chỉ giữ cột băm (`pii_hash`), không giữ PII gốc; `test_nfr_03_no_raw_pii_in_core_and_marts` |
| VI | Unit test và test pytest đặt tên theo FR |

## Quyết định cài đặt

- Hợp đồng staging định nghĩa một chỗ (`scripts/gen_staging_yml.py`), sinh YAML contract và macro `dx_contract()`.
- `dx_union_enabled` tính nguồn đang bật từ `var('sources')` để dbt suy ra phụ thuộc lúc parse.
- Model core/marts chỉ đọc `int_*` (không phụ thuộc nguồn của khách), nên unit test chạy được cho mọi khách.
- Ngày theo giờ Việt Nam: `dateadd(hour, 7, ts)` (Việt Nam không có giờ mùa hè), đa nền tảng.
- `numeric` cho tiền (DuckDB `DECIMAL(18,3)`, BigQuery `NUMERIC`); tỷ lệ phân bổ tính bằng số thực rồi ép về `numeric`.
