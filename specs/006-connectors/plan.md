# Implementation Plan: Nạp dữ liệu sàn

**Branch**: `006-connectors` | **Spec**: [spec.md](spec.md)

## Technical Context

- `pipelines/connectors/common/`: `http.py` (retry, backoff có jitter, 429 theo `Retry-After`, phân loại lỗi), `tokens.py` (đọc/ghi token trong Secret Manager, làm mới), `load.py` (dlt `merge`, cột hợp đồng, bảng rỗng, quét lại đơn mở).
- `pipelines/connectors/{shopee,tiktok_shop}/`: `client.py`, `resources.py`, `schema.py`, `source.py`, `README.md`, `tests/` (fixtures JSON + fake respx).
- `pipelines/connectors/fx_vcb/`: XML Vietcombank qua `defusedxml`, dlt vào `dx_ref.fx_rates`.
- `libs/dx_common/marketplace.py`: chữ ký và OAuth cho Shopee, TikTok Shop, Lazada.
- `services/api/app/routers/connect.py`, `integrations.py`; `knowledge/integrations/*.md`.
- dlt `bigquery` destination dùng credentials đã impersonate service account của khách.

## Constitution Check

- Không bí mật trong code: khóa ứng dụng `dx-<source>-app`, token `dx-<tenant>-<source>-<account>`.
- PII người mua chỉ ở raw (staging băm, không đổi).
- Test chỉ dùng `demo_seller` và fixture giả lập.

## Quyết định cài đặt

ADR 0002 #23–#26.
