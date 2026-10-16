# Feature Specification: Biến đổi và chất lượng dữ liệu (dbt)

**Feature Branch**: `004-dbt-transform`
**Created**: 2026-10-16
**Status**: Implemented
**Input**: `docs/specs/README.md` bước 4 (M0) → `docs/specs/02-transform-and-quality.md` (viết tắt 02)

## User Scenarios & Testing

### US1 – Một dự án dbt chạy riêng cho từng khách (P1)

`dbt build` với biến của khách (02 §1.1) dựng `t_<id>_stg`, `_core`, `_marts`; adapter của nguồn khách không dùng tự tắt.

**Acceptance**: `make dbt-build TENANT=demo_seller` và `TENANT=demo_agency` xanh trên DuckDB (02 §9).

### US2 – Số liệu chuẩn hóa đúng (P1)

1. Trạng thái, lý do hoàn, loại phí map qua seed; trạng thái lạ làm test lỗi; thêm vào file ghi đè thì qua (FR-MOD-01, FR-MOD-04).
2. Tiền USD có `*_original`, `currency`, `*_vnd`; ngày không có tỷ giá dùng ngày làm việc gần nhất trước đó (FR-MOD-03).
3. Giá vốn mới từ ngày X chỉ ảnh hưởng đơn từ X (FR-INP-01).
4. Tổng chi phí trước và sau phân bổ bằng nhau với cả ba cách phân bổ (FR-MOD-05).
5. Không cột nào trong `*_core`, `*_marts` chứa số điện thoại hoặc email gốc (NFR-03).

### US3 – Kiểm tra chất lượng chặn báo cáo (P1)

1. Lệch 2% doanh thu một ngày trong `daily_totals` → `reconcile_daily_totals` lỗi, trả đúng ngày, nguồn, mức lệch (FR-DQ-02).
2. Độ tươi theo `freshness_hours` (FR-DQ-01); bất thường khối lượng ở mức cảnh báo (FR-DQ-03).
3. Marts dựng vào `__staging`, chỉ hoán đổi khi test chặn qua (FR-DQ-04, 02 §6.3).

## Requirements

- **FR-001** (02 §1): `dbt_project.yml`, `profiles.yml` (DuckDB local, BigQuery), `packages.yml`, macro `generate_schema_name`.
- **FR-002** (02 §3): staging cho Shopee, TikTok Shop, Lazada, Amazon Seller, 4 nguồn quảng cáo, portal, tỷ giá; contract enforced.
- **FR-003** (02 §4): 11 model core + model `int_*` trung gian.
- **FR-004** (02 §5): 6 marts.
- **FR-005** (02 §6): test khóa, quan hệ, ánh xạ, tỷ giá, đối soát, phân bổ, khối lượng, thiếu giá vốn.
- **FR-006** (02 §7): `scripts/check_portability.py`.
- **FR-007** (02 §8): unit test dbt cho ánh xạ, quy đổi tiền, giá vốn theo ngày hiệu lực, phân bổ, `is_provisional`, `net_revenue_vnd` khi có hoàn.

## Success Criteria

Toàn bộ 02 §9; xem `transform/tests/test_transform.py`.
