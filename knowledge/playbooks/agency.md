# Playbook gói Agency

Dùng khi trả lời câu hỏi và viết nhận định cho brand hoặc agency chạy quảng cáo đa nền tảng (Meta, TikTok, Google,
Amazon) và bán trên sàn.

## Chọn chỉ số

| Người dùng hỏi | Chỉ số | Ghi chú |
|---|---|---|
| "chi bao nhiêu", "spend" | `ad_spend` | Chia theo `platform`, `campaign` |
| "ROAS" (không nói rõ) | `roas_blended` và `roas_platform` | Nêu cả hai: ROAS thật từ doanh thu thực nhận và ROAS nền tảng tự báo |
| "nền tảng báo cao hơn thực tế" | `platform_vs_actual_gap` | Chênh lệch lớn thường do nền tảng tính trùng chuyển đổi |
| "MER", "hiệu quả marketing tổng" | `mer` | Tổng giá trị bán ÷ chi quảng cáo |
| "CPA", "CPC", "CPM", "CTR" | `cpa`, `cpc`, `cpm`, `ctr` | |
| "ngân sách", "chi có vượt không" | `budget_pacing`, `budget_used_pct`, `spend_mtd`, `budget` | Pacing > 1 là chi nhanh hơn tiến độ |
| "Amazon" | `acos`, `tacos` | Chỉ có khi khách có nguồn Amazon |

## Kỳ thời gian

- Ngân sách và pacing tính theo tháng hiện tại đến hôm qua.
- So sánh tuần với tuần (`compare: previous_period`) hoặc với trung bình 4 tuần (`trailing_4_weeks`).

## Diễn giải

- ROAS nền tảng luôn dễ cao hơn ROAS thật; khi chênh trên ngưỡng `platform_gap_pct` của khách thì nêu rõ.
- Pacing vượt ngưỡng `overspend_pct` thì nhắc giảm ngân sách ngày hoặc dời chiến dịch.
- ROAS giảm hơn `roas_drop_pct` so với 4 tuần thì tìm chiến dịch kéo giảm (chia theo `campaign`).
- Ít lượt nhấp hoặc ít chuyển đổi thì không kết luận mạnh về CPA, ROAS.

## Việc cần làm thường gặp

- Chuyển ngân sách từ chiến dịch ROAS thật thấp sang chiến dịch tốt.
- Giảm ngân sách ngày khi pacing vượt.
- Kiểm tra cấu hình chuyển đổi khi chênh lệch nền tảng và thực tế tăng đột ngột.
