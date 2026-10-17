# Feature Specification: Lớp AI

**Feature Branch**: `013-ai-layer`
**Created**: 2026-10-17
**Status**: Implemented
**Input**: `docs/specs/09-ai-layer.md` (giai đoạn 2), `08-telegram-bot.md` §5–§7, `06-portal.md` §4.4

## User Scenarios & Testing

### US1 – Hỏi đáp trên cổng và Telegram (P1, FR-AI-01, FR-TG-06)

Người dùng hỏi bằng tiếng Việt ở `/app/ask` hoặc gõ tin tự do cho bot; câu trả lời chỉ dùng số từ thư viện chỉ số, có chân trang (chỉ số, phiên bản, kỳ, thời điểm dữ liệu). Cùng câu hỏi trên hai kênh cho cùng câu trả lời khi dữ liệu chưa đổi.

### US2 – Câu hỏi ngoài thư viện (P1, FR-AI-02)

Không có chỉ số phù hợp thì trả lời "Hiện chưa có chỉ số…", ghi `metric_requests`; team xem ở `/ops/metric-requests`.

### US3 – Bảo vệ (P1, FR-TG-08, NFR-01, NFR-03)

Câu hỏi về người mua bị từ chối trước khi gọi model; khách và quyền nằm trong token phiên, không trong tham số của model.

### US4 – Bộ đánh giá (P1, FR-AI-03)

≥ 40 câu mỗi gói; ngưỡng 90% câu đạt, 100% từ chối đúng, 100% chân trang đúng; chạy trong CI khi đổi semantic, ai, playbook, bộ máy hỏi đáp.

### US5 – Agent nội bộ (P2, FR-AGT-01, FR-REP-04)

`weekly-insight` viết bản nháp nhận định, data lead vẫn duyệt; `incident-triage` phân tích lần chạy lỗi; ba agent còn lại là skill Claude Code.

## Requirements

09 §1–§10. Không thêm yêu cầu.
