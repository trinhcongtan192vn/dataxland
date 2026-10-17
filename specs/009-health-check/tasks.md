# Tasks: Kiểm tra sức khỏe dữ liệu

- [x] T001 Đọc file và nhận diện loại; adapter 10 loại file, bỏ PII, băm mã người mua
- [x] T002 Model staging `*_file` và giá vốn từ file; trạng thái tiếng Việt của Shopee trong seed
- [x] T003 Cột hoàn tiền trong file mẫu, bảng `*_file__returns` (ADR 0002 #32)
- [x] T004 Job `healthcheck` chạy trọn trên DuckDB; `healthcheck_convert`
- [x] T005 API công khai: gửi file (honeypot, thời gian điền, giới hạn tần suất), xác nhận, kết quả, đồng ý chuyển
- [x] T006 API vận hành: danh sách, chi tiết, ghi chú, duyệt và gửi, chuyển thành khách (bản nháp qua kiểm tra như CI)
- [x] T007 API nội bộ: start, files, fail, build (kết quả qua bộ máy chỉ số), expired, purged
- [x] T008 Web: trang tải file có hướng dẫn, xác nhận, kết quả, màn duyệt
- [x] T009 Test 07 §10: `pipelines/connectors/files/tests`, `transform/tests/test_healthcheck.py`, `services/api/tests/test_health_checks.py`
