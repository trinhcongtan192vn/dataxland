# Runbook – Telegram không hoạt động (NFR-12, spec 08 §8)

Dấu hiệu: email "[DataxLand] Telegram không gửi được tin" (kênh lỗi kết nối liên tục hơn 30 phút).

1. Kiểm tra `GET https://bot.<domain>/healthz` và `docker compose logs bot`.
2. Kiểm tra mạng của VM tới `api.telegram.org` (Telegram có thể bị nhà mạng chặn tại Việt Nam).
3. Báo cáo tuần vẫn gửi qua email. Mọi tính năng của bot có trên cổng: ba số chính ở dashboard, báo cáo ở
   `/app/reports`.
4. Nếu gián đoạn kéo dài: thông báo cho khách dùng email; cân nhắc thêm kênh (adapter mới trong
   `services/api/app/notify/channels/`, không sửa dispatcher).
5. Khi Telegram hoạt động lại, tin lỗi sau 3 lần thử không tự gửi lại; dùng "Gửi lại" ở `/ops/reports/<id>`.
