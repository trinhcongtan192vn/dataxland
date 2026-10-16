# Feature Specification: Cổng khách hàng – dashboard, sổ tay, nhập liệu, quyết định

**Feature Branch**: `007-portal`
**Created**: 2026-10-17
**Status**: Implemented
**Input**: `docs/specs/README.md` bước 7 (M2) → `docs/specs/06-portal.md` (06) §1–3, §5–7, §9; `05-api-and-auth.md` (05)

## User Scenarios & Testing

### US1 – Đăng nhập và chọn khách (P1)

Người dùng đăng nhập bằng email (có xác minh) hoặc Google; người thuộc nhiều khách chọn khách ở thanh trên (`?t=`), menu theo vai trò từ `GET /v1/me` (06 §2, 05 §3).

### US2 – Dashboard Seller và Agency (P1)

Các khối ở 06 §3.1, §3.2; mỗi khối một lần `POST /v1/metrics/query`, tải và lỗi riêng; bộ lọc ngày/kênh lưu trong URL; thời điểm cập nhật và cảnh báo dữ liệu; bấm tên chỉ số mở định nghĩa; xuất CSV có BOM (FR-DSH-01..05).

### US3 – Sổ tay chỉ số (P1)

Danh sách có tìm kiếm theo tên và từ đồng nghĩa; trang chi tiết với công thức, nguồn, chiều, phiên bản, lịch sử (FR-DSH-04).

### US4 – Nhập giá vốn và ngân sách (P1)

Bảng giá vốn sửa trực tiếp, thêm dòng có ngày hiệu lực, file mẫu, tải file lên với bảng lỗi, hộp SKU thiếu giá vốn; lưới ngân sách tháng × nền tảng (FR-INP-01..04).

### US5 – Nhật ký quyết định (P2)

Tạo quyết định, giá trị trước tự điền qua bộ máy chỉ số; nhắc đo lại; lấy giá trị sau hoặc nhập tay; kết luận (FR-DEC-01, FR-DEC-02).

### US6 – Cài đặt thành viên và agency (P2)

Owner mời/gỡ thành viên, chọn chỉ số cho member; cấp/thu quyền agency (06 §9).

## Requirements

06 §1–3, §5–7, §9; 05 §6. Không thêm yêu cầu. Báo cáo tuần và trang Telegram ở bước 8; trang agency và vận hành ở bước 10.

## Success Criteria

Mọi trang nêu trên chạy với hai khách giả lập; `tsc`, `eslint`, `prettier`, `vitest`, `next build` qua.
