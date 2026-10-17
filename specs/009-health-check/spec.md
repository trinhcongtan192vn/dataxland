# Feature Specification: Kiểm tra sức khỏe dữ liệu

**Feature Branch**: `009-health-check`
**Created**: 2026-10-17
**Status**: Implemented
**Input**: `docs/specs/README.md` bước 9 (M3) → `docs/specs/07-health-check.md` (07)

## User Scenarios & Testing

### US1 – Khách tải file (P1, FR-HC-01)

Trang công khai `/health-check`: email, tên shop, tối đa 10 file (≤ 20 MB, .xlsx/.csv) mỗi file chọn loại, văn bản đồng ý nguyên văn có phiên bản; email xác nhận; file chọn nhầm loại bị từ chối với thông báo đúng.

### US2 – Xử lý bằng cùng pipeline (P1, FR-HC-02, NFR-03)

Khách tạm `hc_<check_id>`: adapter bỏ thông tin người mua khi đọc, cùng dbt, cùng Cube, cùng bộ máy chỉ số gói Seller; kết quả khớp `demo_seller` cùng kỳ.

### US3 – Duyệt và gửi kết quả (P1, FR-HC-03)

Data lead xem trước, ghi chú, duyệt; khách nhận link kết quả không cần đăng nhập; chưa duyệt thì link trả 404.

### US4 – Xóa sau 14 ngày và chuyển thành khách (P1, FR-HC-04, FR-HC-05)

Job dọn dẹp xóa dataset, file, kết quả của lượt quá hạn (trừ lượt đã chuyển); chuyển thành khách sinh bản nháp cấu hình hợp lệ, sao chép raw khi được đồng ý.

## Requirements

07 §2–§9. Không thêm yêu cầu.

## Success Criteria

Mọi test ở 07 §10 qua.
