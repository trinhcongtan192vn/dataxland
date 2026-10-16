# Runbook – `test.failed` (FR-DQ-01..04, spec 02 §6)

Khi có test chặn, khách không nhận số của lần chạy đó: marts không hoán đổi, Cube không làm mới, báo cáo tuần không dựng.
Dashboard vẫn hiện số của lần chạy tốt trước với thời điểm cập nhật cũ.

1. Mở `/ops/tenants/<id>` → "Lỗi chặn": bảng dòng lỗi của test (ngày, nguồn, mức lệch).
2. Theo loại test:
   - `reconcile_daily_totals_<source>`: so số đơn, doanh thu với báo cáo tổng của sàn. Lệch thật thì kiểm tra connector
     (đơn bị thiếu, quét lại 30 ngày); lệch do định nghĩa khác thì cân nhắc `reconcile_tolerance_pct` theo nguồn.
   - `accepted_values` trên `status`/`reason`/`cost_type`: có giá trị mới chưa ánh xạ. Thêm vào seed
     `transform/seeds/*_map__<source>.csv` (mọi khách) hoặc file ghi đè của khách.
   - `not_null` trên `*_vnd`: thiếu tỷ giá. Nhập tay ở `/ops/integrations/vietcombank` (`POST /v1/admin/fx-rates`).
   - `source_freshness`: nguồn quá `freshness_hours`; xem `sync-failed.md`.
   - `sum_preserved`: phân bổ chi phí lệch; báo engineer.
3. Sửa xong thì chạy lại.
