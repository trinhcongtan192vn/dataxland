# Feature Specification: Màn hình vận hành và trang agency

**Feature Branch**: `010-ops-agency`
**Created**: 2026-10-17
**Status**: Implemented
**Input**: `docs/specs/README.md` bước 10 (M3) → `docs/specs/06-portal.md` §8, §10, §11; ADR 0001

## User Scenarios & Testing

### US1 – Màn hình vận hành (P1, FR-OPS-04)

`/ops`: một dòng mỗi khách, ô màu theo nguồn (xanh/vàng/đỏ) kèm thời điểm, test chặn và cảnh báo, báo cáo tuần (trạng thái, đã mở/tổng), tự làm mới 60 giây. `/ops/tenants/[id]`: cấu hình chỉ đọc, nguồn và nút kết nối OAuth, lịch sử chạy, dòng lỗi của test chặn, nút chạy lại.

### US2 – Hướng dẫn tích hợp (P1, ADR 0001)

`/ops/integrations` và trang từng nền tảng: hướng dẫn lấy khóa, trạng thái đã/chưa cấu hình, nguồn của khách đã có token chưa.

### US3 – Trang agency (P1, FR-AGY-01, FR-AGY-02)

`/partner`: các shop đã cấp quyền với chi tiêu tháng, tiến độ ngân sách, ROAS thật, cờ; `/partner/[tenant]`: dashboard gói Agency. Shop thu quyền thì biến mất và gọi trực tiếp bị 403.

### US4 – Kịch bản end-to-end (P2)

Playwright cho các kịch bản 06 §11; tài khoản demo để chạy trên stack local.

## Requirements

06 §8, §10, §11. Không thêm yêu cầu.
