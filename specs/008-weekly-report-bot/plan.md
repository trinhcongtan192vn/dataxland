# Implementation Plan: Báo cáo tuần và Telegram

**Branch**: `008-weekly-report-bot` | **Spec**: [spec.md](spec.md)

## Technical Context

- `services/api/app/reports/builder.py`: snapshot theo gói qua bộ máy chỉ số (tối đa 10 chỉ số mỗi truy vấn: P&L chia hai lần).
- `services/api/app/routers/reports.py`: đọc, sửa, duyệt, thay, gửi lại, người mở, `/v1/ops/reports`, `/r/{token}`, `/v1/internal/reports/build`.
- `services/api/app/routers/telegram.py`: mã liên kết, liên kết, gỡ, `chat-left`, `context`, `messages/{kind}` dựng từ mẫu `bot_*`, giới hạn tần suất bằng `telegram_rate`, khóa mã sai.
- `services/api/app/metrics/key_numbers.py`: `key_numbers_scoped` cho người xem một phần.
- `services/telegram_bot`: FastAPI webhook (`/tg/webhook`, kiểm secret), polling ở local, `Handler` (lệnh, callback, `my_chat_member`), client Bot API và client API qua httpx.
- Web: `/app/reports`, `/app/reports/[id]` (từ snapshot), `/app/settings/telegram`, `/ops/reports`, `/ops/reports/[id]` (nhận định, duyệt, thay, gửi lại, người mở), `/r/[token]` (route handler), `/report-link-invalid`.

## Quyết định

ADR 0002 #27–#31.
