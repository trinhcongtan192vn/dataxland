# Telegram Bot

Bot gửi báo cáo tuần, cảnh báo và trả lời lệnh `/report`, `/week`, `/month` (spec 08).

## 1. Tạo bot

1. Trên Telegram, mở **@BotFather**, gửi `/newbot`.
2. Đặt tên hiển thị (ví dụ `DataxLand`) và username kết thúc bằng `bot` (ví dụ `dataxland_bot`).
3. BotFather trả **token** dạng `123456789:AA...` → biến `TELEGRAM_BOT_TOKEN`. Username (không có `@`) → `TELEGRAM_BOT_USERNAME`.
4. Gửi `/setprivacy` → chọn bot → **Enable** (bot trong nhóm chỉ nhận lệnh, không đọc tin nhắn thường).
5. `/setcommands` → dán:

   ```
   report - Báo cáo tuần mới nhất
   week - Ba số chính tuần này
   month - Ba số chính tháng này
   unlink - Gỡ liên kết chat này
   help - Danh sách lệnh
   ```

## 2. Webhook

- `TELEGRAM_WEBHOOK_SECRET`: chuỗi ngẫu nhiên 32+ ký tự (ví dụ `openssl rand -hex 32`). Telegram gửi lại chuỗi này ở header `X-Telegram-Bot-Api-Secret-Token`.
- `BOT_PUBLIC_URL`: URL công khai của service bot, ví dụ `https://bot.dataxland.vn`. Bot tự đăng ký webhook khi khởi động.
- Ở `local` đặt `BOT_MODE=polling`, không cần URL công khai.

## 3. Nhóm cảnh báo của team

1. Tạo nhóm Telegram cho team, thêm bot vào nhóm.
2. Gửi một tin bất kỳ trong nhóm, rồi mở `https://api.telegram.org/bot<TOKEN>/getUpdates` để xem `chat.id` (số âm, dạng `-100...`).
3. Ghi vào `TELEGRAM_TEAM_CHAT_ID`.

## 4. Khách liên kết Telegram

Khách vào **Cài đặt → Telegram** trên cổng, lấy mã liên kết, gửi cho bot. Không cần thao tác của team.
