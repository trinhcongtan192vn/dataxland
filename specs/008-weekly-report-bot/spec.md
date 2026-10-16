# Feature Specification: Báo cáo tuần, lớp thông báo, Telegram bot

**Feature Branch**: `008-weekly-report-bot`
**Created**: 2026-10-17
**Status**: Implemented
**Input**: `docs/specs/README.md` bước 8 (M3) → `06-portal.md` §4, §9 (Telegram), `04-ops-and-orchestration.md` §3.3, §5, `08-telegram-bot.md`

## User Scenarios & Testing

### US1 – Dựng, viết nhận định, duyệt, gửi báo cáo tuần (P1)

Job `weekly_report` gọi `POST /v1/internal/reports/build`; API ghi snapshot (số, phiên bản chỉ số, `data_as_of`, cảnh báo) cho tuần ISO trước theo gói (06 §4.3); team được báo; data lead viết nhận định và tối đa 5 việc; nút duyệt khóa khi trống; duyệt phát `report.ready`; trung tâm thông báo gửi email (luôn) và Telegram với ba số và nút "Xem báo cáo" (FR-REP-01..05).

### US2 – Ghi nhận mở và lưu trữ (P1)

`/r/<token>` ghi nhận mở theo kênh rồi chuyển tới báo cáo; mở trên cổng ghi `portal`; báo cáo cũ hiển thị từ snapshot, không tính lại; sửa sai bằng bản mới (FR-REP-06, FR-REP-07).

### US3 – Liên kết Telegram và lệnh (P1)

Mã 8 ký tự, 10 phút, dùng một lần; chat riêng và nhóm (owner, phạm vi chỉ số); `/week`, `/month`, `/report`, `/help`, `/unlink`; chọn khách khi chat liên kết nhiều khách; gỡ khi mất quyền, bị xóa, bị chặn; giới hạn tần suất; không có thông tin người mua (FR-TG-01..08).

## Requirements

06 §4, §9; 08 §1–§8; 04 §5. Không thêm yêu cầu.

## Success Criteria

08 §9 và 06 §11 (phần API) qua; web có trang báo cáo, duyệt báo cáo, Telegram.
