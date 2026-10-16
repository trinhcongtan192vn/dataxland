# Anthropic (lớp AI, giai đoạn 2)

Lớp AI (hỏi đáp bằng tiếng Việt, gợi ý quyết định) gọi Claude qua API của Anthropic (spec 09). Mọi đề xuất của AI phải qua bước duyệt của người.

1. Đăng nhập **console.anthropic.com** bằng tài khoản công ty, tạo **Workspace** riêng cho DataxLand.
2. **Settings → Billing**: nạp tiền hoặc gắn thẻ; đặt **spend limit** theo tháng.
3. **API keys → Create key** trong workspace đó → biến `ANTHROPIC_API_KEY` (dev/prod: Secret Manager).
4. Mô hình mặc định: `ANTHROPIC_MODEL_ASK`, `ANTHROPIC_MODEL_AGENT` (mặc định `claude-sonnet-5-5`).

Không gửi thông tin cá nhân người mua sang API: lớp AI chỉ đọc số liệu tổng hợp qua `POST /v1/metrics/query`.
