# 0001 – Màn hướng dẫn lấy thông tin tích hợp trên giao diện

- Trạng thái: Accepted
- Ngày: 2026-10-16
- Feature: toàn bộ (chủ yếu 006, 007, 010)

## Bối cảnh

Tài liệu gốc mô tả việc kết nối nguồn như sau:

- Spec 01 §2.3, spec 05 §6.7: sàn (Shopee, TikTok Shop, Lazada) kết nối bằng OAuth, chỉ `data_lead` bấm từ `/ops/tenants/<id>`.
- Spec 01 §8.2: Windsor là thao tác thủ công theo `ops/runbooks/windsor-setup.md`.
- Spec 04 §9: các runbook `windsor-setup.md`, `marketplace-oauth.md`, `new-tenant.md`.
- Spec 07 §2: trang kiểm tra sức khỏe có hướng dẫn "Xuất file này ở đâu".

Tài liệu gốc không có màn hình trên cổng giải thích cách lấy khóa, token và quyền của từng nền tảng (ứng dụng đối tác Shopee/TikTok Shop/Lazada, Windsor.ai, Telegram BotFather, Firebase, SMTP, Vietcombank, Anthropic).

Ngày 2026-10-16 chủ dự án yêu cầu: "Với các phần tích hợp ở các nền tảng liên quan, làm nhiều nhất có thể phần phát triển và có màn hướng dẫn trên giao diện để người dùng biết cách lấy thông tin (key, token, auth) để tích hợp."

## Quyết định

Thêm vào cổng (chỉ vai trò nội bộ, `ops.read`) khu vực `/ops/integrations` và `/ops/integrations/<nền tảng>`:

- Mỗi nền tảng một trang: cần gì, lấy ở đâu (từng bước), biến môi trường hoặc secret nào nhận giá trị đó (tên secret theo spec 01 §2.2, spec 05 §6.7), cách kiểm tra đã đúng.
- Trạng thái cấu hình đọc từ API (`GET /v1/ops/integrations`): chỉ trả "đã cấu hình / chưa cấu hình" cho từng biến, không bao giờ trả giá trị (spec 00 §3.4, §3.5).
- Nội dung hướng dẫn nằm trong `knowledge/integrations/<nền tảng>.md` và được runbook trong `ops/runbooks/` dẫn tới, để chỉ có một nguồn nội dung.
- `/ops/tenants/<id>` dẫn tới trang hướng dẫn tương ứng cạnh nút kết nối của mỗi nguồn.

Không thay đổi hành vi nào khác của tài liệu gốc: nhập khóa vẫn qua Secret Manager hoặc `.secrets/`, không có ô nhập bí mật trên cổng.

## Hệ quả

- Thêm một endpoint chỉ đọc `GET /v1/ops/integrations` (quyền `ops.read`).
- Thêm thư mục `knowledge/integrations/`.
