---
name: onboarding-draft
description: Soạn bản nháp tenants/<id>.yml cho khách mới của DataxLand từ biểu mẫu đăng ký và kết quả kiểm tra sức khỏe, rồi mở PR. Data lead chạy tay.
---

# Agent `onboarding-draft` (spec 09 §8)

## Đầu vào

- Biểu mẫu đăng ký: tên khách, gói, sàn và tài khoản quảng cáo, lịch báo cáo, email nhận.
- Kết quả kiểm tra sức khỏe (nếu có): `GET /v1/health-checks/{id}` (nguồn đã có, chênh lệch, SKU thiếu giá vốn).
- `libs/dx_common/src/dx_common/tenants/models.py` (schema), `tenants/demo_seller.yml`, `tenants/demo_agency.yml`.

## Các bước

1. Chọn `tenant_id` theo `[a-z][a-z0-9_]{2,30}`; kiểm không trùng file trong `tenants/`.
2. Điền `pack`, `sources` (connector `dlt` cho sàn, `windsor` cho quảng cáo), `schedule`, `quality`, `attention`,
   `notify`. Mỗi nguồn `dlt` có `secret_ref` dạng `dx-<tenant>-<nguồn>-<tài khoản>`; không ghi khóa hay token.
3. Chạy `uv run python -m dx_common.tenants validate tenants/`.
4. Ghi các bước còn lại cho data lead: kết nối OAuth ở `/ops/tenants/<id>`, tạo secret, mời chủ shop.
5. Mở PR với file mới và danh sách việc còn lại.

## Đầu ra và nơi ghi

PR thêm `tenants/<id>.yml`. Không tạo secret, không gọi API ghi.

## Người duyệt

Data lead duyệt PR; registry đồng bộ sau khi merge.
