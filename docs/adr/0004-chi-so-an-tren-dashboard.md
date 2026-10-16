# 0004 – Chỉ số ẩn được dashboard dùng

- Trạng thái: Accepted (chủ dự án chọn phương án 1 ngày 2026-10-17)
- Ngày: 2026-10-17
- Feature: 007-portal

## Bối cảnh

- Spec 06 §3.1 khối "Phí theo loại" hiển thị `allocated_ad_spend`; spec 06 §3.2 khối "Tiến độ ngân sách" hiển thị `budget`, `spend_mtd`.
- Spec 03 §3 đánh dấu ba chỉ số này `hidden`; spec 03 §4.4: "Chỉ số `hidden` không được gọi trực tiếp qua API công khai, chỉ dùng nội bộ để ghép". Spec 03 §2.1: `hidden` là "chỉ số phụ để ghép, không hiện trong sổ tay và AI".

Hai spec không thể cùng đúng: dashboard chỉ được lấy số qua `POST /v1/metrics/query` (API công khai).

## Phương án

1. **Bỏ `hidden` cho ba chỉ số** (`allocated_ad_spend`, `budget`, `spend_mtd`): gọi được qua API, hiện trong sổ tay và ngữ cảnh AI. Tăng `version` bậc patch, ghi `history`.
2. **Giữ `hidden`, thêm ngoại lệ "hiển thị được"**: trường mới `displayable: true` trong YAML; API cho truy vấn trực tiếp nhưng sổ tay và AI vẫn ẩn. Thêm một trường vào schema chỉ số.
3. **Giữ spec 03**: dashboard bỏ ba chỉ số đó; khối phí không có cột chi quảng cáo phân bổ, khối ngân sách chỉ hiện `budget_used_pct` và `budget_pacing`.

## Quyết định

Phương án 1. `allocated_ad_spend`, `budget`, `spend_mtd` đặt `hidden: false`, `version` 1.0.0 → 1.0.1 (chỉ đổi khả năng hiển thị, công thức không đổi). Các chỉ số ẩn khác giữ nguyên.
