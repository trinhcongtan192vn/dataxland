# 0003 – Elementary trên DuckDB

- Trạng thái: Proposed (đang dùng phương án 1, chờ chủ dự án chốt)
- Ngày: 2026-10-16
- Feature: 004-dbt-transform

## Bối cảnh

- Spec 02 §6.1: "Khối lượng | Elementary `volume_anomalies` trên `fct_order`, `fct_ad_performance_daily` | Cảnh báo | FR-DQ-03".
- Spec 00 §2: dùng gói `elementary`. Spec 00 §8.1, NFR-07: CI chạy toàn bộ model trên DuckDB.

Khi cài đặt: gói `elementary-data/elementary` 0.21.0 lỗi khi dựng các model artifact trên DuckDB (lỗi escape chuỗi
`\'` trong `dbt_columns`, `dbt_models` và lỗi transaction lồng nhau trong `dbt_seeds`). Vì vậy không thể vừa chạy
Elementary vừa giữ CI trên DuckDB như spec yêu cầu.

## Các lựa chọn

1. **Elementary chỉ bật trên BigQuery (dev, prod); trên DuckDB dùng test tự viết `dx_volume_anomaly`** cùng ý tưởng
   (số dòng hôm qua so với trung bình ± 3 độ lệch chuẩn của 28 ngày trước), mức cảnh báo. CI vẫn chạy trên DuckDB.
2. Bỏ Elementary, dùng `dx_volume_anomaly` ở mọi môi trường.
3. Giữ Elementary ở mọi nơi và chuyển bước dbt của CI sang BigQuery `dev` (tốn chi phí, cần tài khoản dịch vụ trong CI).

## Quyết định

Đang cài theo phương án 1 (gần spec nhất). Chờ chủ dự án chốt.

## Hệ quả

- `transform/dbt_project.yml`: model của Elementary chỉ bật khi `target.type == 'bigquery'`.
- `transform/models/core/_core.yml`: mỗi bảng có hai test, chỉ một test bật theo kho.
