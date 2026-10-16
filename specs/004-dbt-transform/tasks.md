# Tasks: Biến đổi và chất lượng dữ liệu

- [x] T001 Khung dự án dbt, profiles, packages, macro schema/alias (marts `__staging`), query comment có nhãn
- [x] T002 Macro đa nền tảng, `to_vnd`, `pii_hash`, `dx_union_enabled`, `dx_swap_marts`
- [x] T003 Seed ánh xạ trạng thái, lý do hoàn, loại phí, nền tảng
- [x] T004 `sources.yml` sinh tự động, độ tươi theo `freshness_hours`
- [x] T005 Staging 8 nguồn + portal + tỷ giá, contract sinh tự động
- [x] T006 Core: `int_*`, 6 dim, 6 fct
- [x] T007 Marts: 6 bảng
- [x] T008 Test generic `reconcile_daily_totals`, `sum_preserved`, `dx_volume_anomaly`; singular thiếu giá vốn
- [x] T009 Unit test dbt (17 test)
- [x] T010 `scripts/check_portability.py`, `.sqlfluff`
- [x] T011 `transform/tests/test_transform.py`: tiêu chí 02 §9, tách biệt khách 00 §9.3
- [x] T012 `ops/dbt_build.py` cho `make dbt-build`
- [x] T013 ADR 0003 Accepted: Elementary trên BigQuery, `dx_volume_anomaly` trên DuckDB
