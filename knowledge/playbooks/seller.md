# Playbook gói Seller

Dùng khi trả lời câu hỏi và viết nhận định cho chủ shop bán đa kênh (Shopee, TikTok Shop, Lazada).

## Chọn chỉ số

| Người dùng hỏi | Chỉ số | Ghi chú |
|---|---|---|
| "lãi", "lời", "lãi thật" | `net_profit_after_fees` | Đã trừ giá vốn, phí sàn, phí thanh toán, vận chuyển, hoàn hàng, quảng cáo phân bổ, chi phí khác |
| "doanh thu", "tiền về" | `net_revenue` | Doanh thu thực nhận sau giảm giá shop chịu; không phải GMV |
| "doanh số", "GMV" | `gmv` | Tổng giá trị đơn trước hủy, hoàn |
| "biên lãi", "margin" | `net_margin_pct` | Lãi sau phí ÷ Doanh thu thực nhận |
| "phí sàn ăn bao nhiêu" | `platform_fees`, `payment_fees` | Có thể chia theo `channel` |
| "quảng cáo có lời không" | `roas_blended`, `allocated_ad_spend` | ROAS thật dùng doanh thu thực nhận, không dùng số nền tảng báo |
| "sản phẩm nào lỗ" | `sku_profit` theo `sku` | Sắp xếp tăng dần để thấy SKU lỗ |
| "hoàn hàng" | `return_rate`, `return_cost` | |
| "hủy đơn" | `cancel_rate` | |
| "khách quay lại" | `repeat_customer_rate` | Chỉ có khi khách bật ghép định danh |

## Kỳ thời gian

- "tuần này" = `this_week` (từ thứ Hai đến hôm qua), "tuần trước" = `last_week`, "tháng này" = `this_month`.
- So sánh thì dùng `compare: previous_period`; nói rõ tăng hay giảm bao nhiêu % và số tuyệt đối.
- Không có kỳ thì mặc định 30 ngày gần nhất và nói rõ kỳ đó trong câu trả lời.

## Diễn giải

- Lãi giảm: tách nguyên nhân theo thành phần (giá vốn, phí sàn, ship, hoàn, quảng cáo) và theo `channel`.
- Cảnh báo `MISSING_COGS`: lãi đang cao hơn thực tế vì một số SKU chưa có giá vốn; nhắc nhập ở trang Nhập liệu.
- Cảnh báo `PROVISIONAL`: một phần doanh thu chưa quyết toán, số có thể đổi khi sàn quyết toán.
- Cảnh báo `STALE`: dữ liệu cũ hơn ngưỡng, nói rõ thời điểm dữ liệu.
- Thay đổi nhỏ hơn 5% tuần so với tuần thường là dao động bình thường; không kết luận mạnh.

## Việc cần làm thường gặp

- Nhập giá vốn cho SKU còn thiếu.
- Tắt hoặc giảm giá thầu quảng cáo cho SKU lỗ sau phí.
- Xem lại chương trình giảm giá shop chịu khi biên lãi giảm mà doanh thu tăng.
- Kiểm tra tỷ lệ hoàn theo kênh khi chi phí hoàn tăng.
