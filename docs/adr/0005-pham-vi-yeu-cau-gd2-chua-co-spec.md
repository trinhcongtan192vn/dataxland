# 0005 – Phạm vi các yêu cầu PRD chưa có spec chi tiết

- Trạng thái: Accepted (chủ dự án chọn phương án đề xuất cho cả bốn mục ngày 2026-10-17)
- Ngày: 2026-10-17
- Feature: 015-carriers, 016-agency-weekly, 017-tenant-setup-form, 018-contract-value-report

## Bối cảnh

PRD có bốn yêu cầu P2 mà spec chưa mô tả đủ để cài:

- FR-ING-09 "Connector hãng vận chuyển (GHN, GHTK, J&T) – Phí và COD theo vận đơn khớp file đối soát của hãng".
  Spec 01 §9: "Bảng `<carrier>__shipments` (khóa mã vận đơn) với phí vận chuyển, COD, trạng thái, phí hoàn. Chi tiết
  viết khi bắt đầu giai đoạn 2."
- FR-AGY-03 "Báo cáo tuần gộp cho agency (nhiều shop)". Spec 06 §4: "FR-AGY-03 … ở giai đoạn 2."
- FR-OPS-07 "Biểu mẫu thiết lập sinh bản nháp cấu hình, mở PR". Không spec nào mô tả.
- FR-DEC-04 "Báo cáo giá trị cuối kỳ hợp đồng". Spec 06 §7.2: "… ở giai đoạn sau."

## Các lựa chọn và quyết định

| Yêu cầu | Phương án được chọn | Phương án khác |
|---|---|---|
| FR-ING-09 | Connector GHN và GHTK qua API (token), J&T qua file đối soát Excel bằng khung tải file sẵn có; bảng `<hãng>__shipments`; đối soát phí và COD theo vận đơn | Chỉ file đối soát cho cả ba hãng; hoãn |
| FR-AGY-03 | Mỗi agency một báo cáo mỗi tuần ghép số đã khóa của các báo cáo shop đã duyệt; gửi email và Telegram cho người của agency khi mọi báo cáo thành phần đã duyệt; xem ở `/partner/reports` | Chỉ trang tổng hợp; hoãn |
| FR-OPS-07 | Form `/ops/tenants/new` sinh `tenants/<id>.yml`, kiểm tra schema; có `GITHUB_TOKEN` thì API mở PR, không có thì tải file; không ghi bí mật | Chỉ sinh YAML; hoãn |
| FR-DEC-04 | Nhập ngày bắt đầu và kết thúc hợp đồng của khách; trang tổng kết quyết định trong kỳ (giá trị trước/sau, kết luận) lấy số qua bộ máy chỉ số; tải về PDF | Hoãn tới giai đoạn 3 |

## Hệ quả

- Mỗi yêu cầu là một feature spec-kit riêng; chi tiết cài đặt tự quyết ghi ở ADR 0002.
- FR-DEC-03 (tự lấy giá trị sau) và FR-BMK-01 (so sánh ngành) vẫn ở giai đoạn 3, chưa làm.
