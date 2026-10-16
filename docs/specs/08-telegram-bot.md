# Spec 08 – Telegram bot

Hệ thống: S6b. Yêu cầu: FR-TG-01..08, FR-REP-05..06 (kênh Telegram), NFR-11, NFR-12.

Phạm vi: dịch vụ `services/telegram_bot`, liên kết tài khoản, lệnh, nhóm, giới hạn tần suất. Việc gửi báo cáo và cảnh báo chủ động do trung tâm thông báo làm (spec 04 mục 5) qua adapter `TelegramChannel`, dùng cùng bot token.

Nguyên tắc: bot không có logic nghiệp vụ và không giữ trạng thái. Mọi việc gọi `services/api` với danh tính của chat đã liên kết (spec 05 mục 3.4). Nội dung tin do API dựng từ cùng bộ mẫu với trung tâm thông báo.

---

## 1. Cấu trúc dịch vụ

```
services/telegram_bot/
  pyproject.toml
  bot/
    main.py           # FastAPI nhỏ nhận webhook; aiogram 3 Dispatcher
    handlers/
      start.py  commands.py  callbacks.py  membership.py  free_text.py
    api_client.py     # gọi services/api với INTERNAL_API_TOKEN + X-Telegram-Chat-Id
    send.py           # gửi tin đã dựng, chia tin dài, escape HTML
  tests/
```

- Nhận cập nhật qua webhook `POST /tg/webhook` (Caddy định tuyến `bot.<domain>`). Kiểm tra header `X-Telegram-Bot-Api-Secret-Token` bằng `TELEGRAM_WEBHOOK_SECRET`; sai thì trả 401.
- Khi khởi động: gọi `setWebhook` với `secret_token`, `allowed_updates = [message, callback_query, my_chat_member]`, và `setMyCommands` với danh sách lệnh tiếng Việt (mục 4).
- Ở `local`: chạy chế độ long polling (`BOT_MODE=polling`) với bot thử nghiệm riêng.
- Bật privacy mode của bot (qua BotFather): trong nhóm, bot chỉ nhận lệnh, không đọc tin thường.
- Log: chỉ ghi loại cập nhật, lệnh, `chat_id` dạng hash, mã lỗi. Không ghi nội dung tin tự do.

## 2. Dịch vụ phía API

Bot gọi các endpoint sau (token nội bộ, `X-Service: bot`, `X-Telegram-Chat-Id`):

| Method | Đường dẫn | Mô tả |
|---|---|---|
| `POST` | `/v1/telegram/links` | Đổi mã lấy liên kết: `{code, chat_id, chat_type, chat_title?, telegram_user_id}` |
| `POST` | `/v1/telegram/unlink` | Gỡ liên kết của chat (một khách hoặc tất cả) |
| `POST` | `/v1/telegram/chat-left` | Bot bị xóa khỏi nhóm hoặc bị người dùng chặn |
| `GET` | `/v1/telegram/context` | Các khách mà chat này đã liên kết, vai trò, phạm vi |
| `POST` | `/v1/telegram/messages/{kind}` | API dựng tin sẵn để gửi. `kind`: `key_numbers`, `latest_report`, `help`, `not_linked`, `link_ok`, `link_error`, `rate_limited`, `choose_tenant`. Body: `{tenant_id?, period?}`. Trả `{text_html, buttons: [{label, url? , callback_data?}]}` |
| `POST` | `/v1/ask` | Giai đoạn 2 (spec 09) |

`/v1/telegram/messages/*` dùng các mẫu trong `services/api/app/notify/templates/` (bản `telegram.html.j2`), nên tin trả lời lệnh và tin gửi chủ động có cùng định dạng.

## 3. Liên kết tài khoản (FR-TG-01, FR-TG-04, FR-TG-05)

### 3.1 Dữ liệu

| Bảng | Cột chính |
|---|---|
| `telegram_link_codes` | `id`, `code_hash`, `user_id`, `tenant_id`, `kind` (`private` \| `group`), `metric_scope` (text[] \| null), `expires_at` (= tạo + 10 phút), `used_at`, `attempts` |
| `telegram_links` | `id`, `chat_id` (bigint), `chat_type` (`private`, `group`, `supergroup`), `chat_title`, `telegram_user_id`, `user_id` (người tạo mã), `tenant_id`, `metric_scope` (text[] \| null), `status` (`active`, `revoked`), `linked_at`, `revoked_at`, `revoked_reason` (`user_unlink`, `owner_removed`, `access_lost`, `bot_removed`, `bot_blocked`) |

Unique (`chat_id`, `tenant_id`) với `status = active`. Một chat riêng có thể liên kết với nhiều khách nếu người dùng thuộc nhiều khách.

### 3.2 Mã liên kết

- Tạo bởi `POST /v1/telegram/link-codes` (spec 05 mục 6.8). Mã 8 ký tự từ bảng chữ `ABCDEFGHJKMNPQRSTUVWXYZ23456789`, lưu dạng hash.
- `kind = group` chỉ owner tạo được, và phải gửi `metric_scope` (danh sách chỉ số không ẩn của gói, ít nhất một).
- Response: `{code, expires_at, deep_link}`. `deep_link`: chat riêng `https://t.me/<bot>?start=<code>`; nhóm `https://t.me/<bot>?startgroup=<code>`.
- Mã dùng một lần. Mã sai quá 5 lần trên một chat trong 10 phút → chat đó bị khóa liên kết 30 phút.

### 3.3 Đổi mã (bot nhận `/start <code>`)

API kiểm tra theo thứ tự, lỗi nào trả `link_error` với lý do tiếng Việt tương ứng:

| Kiểm tra | Mã lỗi |
|---|---|
| Mã tồn tại | `CODE_INVALID` |
| Chưa dùng, chưa hết hạn | `CODE_EXPIRED` |
| `kind` khớp loại chat (`private` ↔ chat riêng; `group` ↔ nhóm) | `CODE_WRONG_CHAT_TYPE` |
| Người tạo mã vẫn có quyền với khách (và vẫn là owner với `group`) | `ACCESS_LOST` |

Thành công: tạo `telegram_links`, đặt `used_at`, phát `telegram.linked`, ghi `audit_log`, trả `link_ok` ("Đã liên kết với <tên shop>. Gõ /week để xem số tuần này.").

### 3.4 Chat chưa liên kết

Mọi tin và lệnh (trừ `/start <mã>` và `/help`) từ chat chưa liên kết nhận tin `not_linked`: hướng dẫn vào `/app/settings/telegram` để tạo mã. Không gửi bất kỳ số liệu nào.

### 3.5 Gỡ liên kết

- `/unlink` trong chat: bot hỏi xác nhận bằng nút; nếu chat liên kết nhiều khách thì cho chọn khách hoặc "Tất cả". Xác nhận → `POST /v1/telegram/unlink`.
- Trên cổng: người dùng gỡ liên kết của mình; owner gỡ mọi liên kết của khách.
- Tự động: người dùng mất quyền với khách (spec 05 mục 3.4), bot bị xóa khỏi nhóm hoặc bị chặn (`my_chat_member`).
- Sau khi gỡ: phát `telegram.unlinked`; tin kế tiếp của chat đó nhận `not_linked`.

### 3.6 Nhóm (FR-TG-05)

- Chỉ owner tạo được mã nhóm, kèm phạm vi chỉ số.
- Trong nhóm, quyền theo phạm vi của liên kết, không theo người gõ lệnh. Bất kỳ thành viên nào của nhóm gõ lệnh đều nhận câu trả lời trong phạm vi đó.
- Lệnh trả về chỉ số ngoài phạm vi: số đó được thay bằng "—" kèm ghi chú "ngoài phạm vi của nhóm".
- Tin chủ động (báo cáo tuần, cảnh báo) gửi vào nhóm theo quy tắc spec 04 mục 5.3.
- Owner liên kết nhóm mất vai trò owner → liên kết nhóm bị gỡ (`owner_removed`), team được báo.

## 4. Lệnh (FR-TG-03)

| Lệnh | Việc | Gọi API |
|---|---|---|
| `/start <mã>` | Liên kết | `POST /v1/telegram/links` |
| `/report` | Báo cáo tuần mới nhất đã gửi: ba số chính và nút "Xem báo cáo" | `POST /v1/telegram/messages/latest_report` |
| `/week` | Ba số chính của tuần hiện tại (thứ Hai đến hôm qua; thứ Hai thì là tuần trước) | `POST /v1/telegram/messages/key_numbers {period: this_week}` |
| `/month` | Ba số chính của tháng hiện tại đến hôm qua | `… {period: this_month}` |
| `/help` | Danh sách lệnh, link cổng | `… /help` |
| `/unlink` | Gỡ liên kết | `POST /v1/telegram/unlink` |

- Chat liên kết nhiều khách: lệnh trả tin `choose_tenant` với nút cho từng khách; bấm nút (callback `kt:<cmd>:<tenant_id>`) thì chạy lệnh cho khách đó. API kiểm tra lại quyền khi xử lý callback.
- Mọi tin số liệu có dòng cuối "Cập nhật lúc HH:mm dd/mm" từ `data_as_of`, và cảnh báo dữ liệu dạng ngắn nếu có.
- Số trong lệnh lấy từ `GET /v1/metrics/key-numbers`, cùng hàm với cổng và báo cáo, nên khớp với cổng tại cùng thời điểm.
- `/report` tạo (nếu chưa có) một `report_recipients` kênh `telegram` cho liên kết này, để nút "Xem báo cáo" ghi nhận mở với `via = telegram_button` (FR-REP-06).

Ví dụ `/week` (gói Seller):

```
Tuần này (13/10–15/10) – Shop Demo
• Doanh thu thực nhận: 64.120.000 ₫
• Lãi sau phí: 7.850.000 ₫
• Lãi so với cùng kỳ tuần trước: ▲ 4,2%
⚠️ 2 SKU chưa có giá vốn
Cập nhật lúc 09:05 16/10
[Mở dashboard]
```

## 5. Tin nhắn tự do (FR-TG-06)

- Giai đoạn 1: chat riêng đã liên kết gửi tin không phải lệnh → bot trả `help` kèm câu "Tính năng hỏi đáp bằng câu tự do sẽ sớm có. Hiện bạn dùng /week, /month, /report.". Không gọi AI. Trong nhóm, privacy mode nên bot không nhận tin thường.
- Giai đoạn 2: chuyển câu hỏi tới `POST /v1/ask` với ngữ cảnh của chat (spec 09). Bot gửi `sendChatAction typing` trong lúc chờ, rồi gửi câu trả lời. Trong nhóm, câu hỏi phải bắt đầu bằng `/ask` hoặc nhắc tên bot.

## 6. Giới hạn tần suất (FR-TG-07)

Áp dụng ở API cho mọi request có `X-Telegram-Chat-Id`, lưu trong bảng `telegram_rate` (cửa sổ trượt).

| Loại | Giới hạn mặc định |
|---|---|
| Lệnh | 20 lần mỗi 10 phút mỗi chat |
| Câu hỏi AI (GĐ2) | 10 lần mỗi giờ mỗi chat; 50 lần mỗi ngày mỗi khách |
| Mã liên kết sai | Mục 3.2 |

Vượt giới hạn → API trả `429` kèm tin `rate_limited` ("Bạn thao tác hơi nhanh, thử lại sau N phút."). Với câu hỏi AI, kiểm tra giới hạn diễn ra trước khi gọi model.

Giới hạn cấu hình được trong biến môi trường của API (`TG_RATE_COMMANDS`, `TG_RATE_ASK_CHAT`, `TG_RATE_ASK_TENANT`).

## 7. Không có thông tin người mua (FR-TG-08)

- Mọi tin bot gửi được dựng từ số tổng hợp của bộ máy chỉ số và mẫu tin; mẫu không có biến nào chứa thông tin người mua (spec 04 mục 5.2).
- Giai đoạn 1 không có đường nào để hỏi về một người mua cụ thể.
- Giai đoạn 2: bộ máy hỏi đáp từ chối câu hỏi về người mua cụ thể (spec 09 mục 5); bộ đánh giá AI có câu kiểm tra việc này.

## 8. Telegram không hoạt động (NFR-12)

- Bot có `GET /healthz` gọi `getMe`; lỗi liên tục được trung tâm thông báo báo cho team qua email (spec 04 mục 5.4).
- Mọi tính năng của bot có trên cổng: ba số chính ở dashboard, báo cáo ở `/app/reports`, liên kết và gỡ ở `/app/settings/telegram`.
- Báo cáo tuần luôn gửi qua email song song.

## 9. Kiểm thử

Test dùng bộ giả lập Bot API (`respx`) và gửi cập nhật giả vào webhook.

| Test | Nội dung | FR |
|---|---|---|
| `test_fr_tg_01_link_with_valid_code` | Mã đúng tạo liên kết, phát `telegram.linked` | FR-TG-01 |
| `test_fr_tg_01_code_used_or_expired` | Mã đã dùng hoặc quá 10 phút bị từ chối | FR-TG-01 |
| `test_fr_tg_01_unlinked_chat_gets_no_numbers` | Chat chưa liên kết gõ `/week` chỉ nhận hướng dẫn | FR-TG-01 |
| `test_fr_tg_02_report_ready_delivered` | `report.ready` tạo tin Telegram có nút xem báo cáo cho mọi liên kết của khách | FR-TG-02 |
| `test_fr_tg_03_week_matches_portal` | Số của `/week` bằng `GET /v1/metrics/key-numbers?period=this_week` cùng thời điểm | FR-TG-03 |
| `test_fr_tg_04_unlink_then_not_linked` | Sau `/unlink`, tin kế tiếp nhận `not_linked` | FR-TG-04 |
| `test_fr_tg_04_access_lost_unlinks` | Owner gỡ member, chat của member hết nhận số | FR-TG-04 |
| `test_fr_tg_05_group_scope` | Nhóm với phạm vi `[net_revenue]` thấy `net_revenue`, các số khác là "—" | FR-TG-05 |
| `test_fr_tg_05_group_code_owner_only` | Member tạo mã nhóm → 403 | FR-TG-05 |
| `test_fr_tg_07_rate_limit` | Lệnh thứ 21 trong 10 phút nhận `rate_limited` | FR-TG-07 |
| `test_fr_tg_08_no_buyer_pii_in_templates` | Quét mẫu tin: không có biến tên chứa `phone`, `email`, `address`, `buyer` | FR-TG-08 |
| `test_isolation_telegram` | Chat liên kết `demo_seller` không bao giờ nhận số `demo_agency` (spec 00 mục 9) | NFR-01 |
| `test_webhook_secret_required` | Thiếu hoặc sai secret → 401 | |

## 10. Tiêu chí hoàn thành

- Trên `dev` với bot thử nghiệm: liên kết chat riêng và nhóm, chạy đủ lệnh ở mục 4, nhận báo cáo tuần sau khi duyệt, gỡ liên kết.
- Mọi test ở mục 9 qua.
