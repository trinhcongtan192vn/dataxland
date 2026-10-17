---
name: new-adapter
description: Dựng connector nguồn mới cho DataxLand (dlt, staging dbt, seed ánh xạ, test, dữ liệu mẫu) rồi mở PR. Engineer chạy tay khi thêm một sàn hoặc nền tảng quảng cáo.
---

# Agent `new-adapter` (spec 09 §8)

## Đầu vào

- Tên nguồn (`source_type`), tài liệu API của nền tảng, loại kết nối (OAuth, khóa API, file xuất).
- Hợp đồng raw bắt buộc: `docs/specs/01-ingestion.md` §1, §2.1.

## Các bước

1. Đọc `docs/specs/00-foundation.md`, `01-ingestion.md`, `02-transform-and-quality.md` và một connector mẫu gần nhất
   (`pipelines/connectors/shopee/` cho sàn, `pipelines/connectors/files/` cho file xuất).
2. Tạo `pipelines/connectors/<nguồn>/`: `client.py` (ký, làm mới token, phân loại lỗi `AUTH_EXPIRED`,
   `RATE_LIMITED`, `SCHEMA_CHANGED`), `resources.py`, `schema.py`, `source.py`, `README.md`. Bí mật chỉ qua
   `secret_ref` và `dx_common.secrets`.
3. Thêm hướng dẫn lấy khóa vào `knowledge/integrations/<nguồn>.md` (hiện ở `/ops/integrations`).
4. Tạo staging `transform/models/staging/<nguồn>/stg_<nguồn>__*.sql`; hàm riêng của BigQuery chỉ được dùng ở đây.
   Thông tin người mua băm ngay ở staging; thêm cột vào `transform/pii_columns.yml`.
5. Seed ánh xạ `status_map__<nguồn>.csv`, `fee_type_map__<nguồn>.csv`, `return_reason_map__<nguồn>.csv`.
6. Dữ liệu mẫu `transform/samples/` cho `demo_seller` hoặc `demo_agency` (không dùng dữ liệu khách thật).
7. Test: connector bằng `respx` (hợp đồng raw, token hết hạn, 429, quét lại), dbt unit test cho staging. Tên test có
   mã yêu cầu (`test_fr_ing_0x_...`).
8. Chạy `make lint`, `make test`; mở PR, mô tả nguồn, bảng raw, giới hạn API.

## Đầu ra và nơi ghi

PR trên nhánh riêng. Không sửa `semantic/cube/`, `semantic/dist/` bằng tay.

## Người duyệt

Data lead và một engineer khác.
