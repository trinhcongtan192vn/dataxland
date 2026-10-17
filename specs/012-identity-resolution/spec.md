# Feature Specification: Ghép định danh sản phẩm và người mua

**Feature Branch**: `012-identity-resolution`
**Created**: 2026-10-17
**Status**: Implemented
**Input**: `docs/specs/10-identity-resolution.md` (giai đoạn 2), `03-semantic-layer.md` §4.4, `04-ops-and-orchestration.md` §8

## User Scenarios & Testing

### US1 – Ghép sản phẩm xuyên kênh (P1, FR-ID-01)

Cùng mã vạch hoặc cùng SKU chuẩn hóa thì tự duyệt. Tên gần giống thì worker gợi ý (độ giống + Claude so cặp), data lead duyệt, từ chối, duyệt hàng loạt hoặc gỡ ở `/ops/tenants/<id>/matches`. Gợi ý không bao giờ tự vào `identity_map`.

### US2 – Ghép người mua (P1, FR-ID-02)

Ghép bằng quy tắc trên `phone_hash`, `email_hash`, cùng nguồn + `buyer_ref`; `dim_customer.customer_id` gộp sau khi dbt chạy lại. Khách bật `features.identity` thì có `active_customers`, `repeat_customers`, `repeat_customer_rate`.

### US3 – Bảo vệ dữ liệu cá nhân (P1, NFR-03)

Worker chỉ đọc cột băm; payload gửi model chỉ có trường sản phẩm; xóa dữ liệu người mua thì xóa cả dòng `identity_map`.

## Requirements

10 §1–§10; 03 §4.4; 04 §8. Không thêm yêu cầu.
