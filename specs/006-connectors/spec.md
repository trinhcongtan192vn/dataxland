# Feature Specification: Nạp dữ liệu sàn, tỷ giá, kết nối OAuth

**Feature Branch**: `006-connectors`
**Created**: 2026-10-17
**Status**: Implemented
**Input**: `docs/specs/README.md` bước 6 (M1) → `docs/specs/01-ingestion.md` (01), `05-api-and-auth.md` §6.7, ADR 0001

## User Scenarios & Testing

### US1 – Nạp Shopee và TikTok Shop (P1)

Connector dlt nạp đơn, dòng đơn, quyết toán, trả hàng, sản phẩm và tổng theo ngày vào `t_<id>_raw` đúng hợp đồng (FR-ING-01, FR-ING-02).

**Acceptance**: với API giả lập: phân trang, làm mới token, 429, mất quyền, quét lại đơn đổi trạng thái; mọi bảng có `_dx_loaded_at`, `_dx_source_account`, `_dx_record_hash`. Trên `dev` khớp Seller Centre trong 1% (cần shop thử nghiệm).

### US2 – Hành vi bắt buộc của connector (P1)

Lịch sử 90 ngày theo cửa sổ 7 ngày (FR-ING-05), tăng dần theo con trỏ (FR-ING-06), quét lại đơn mở 30 ngày (FR-ING-07), làm mới token và `auth_revoked` (FR-ING-08), không log body.

### US3 – Tỷ giá (P1)

`fx_vcb` nạp tỷ giá bán ra USD hằng ngày vào `dx_ref.fx_rates`; lỗi phát `sync.failed` (FR-MOD-03).

### US4 – Kết nối gian hàng (P1)

`data_lead` bấm Kết nối, chủ shop đồng ý trên sàn, API ghi token vào Secret Manager và cập nhật `source_syncs` (spec 05 §6.7).

### US5 – Hướng dẫn tích hợp (P2, ADR 0001)

`GET /v1/ops/integrations` trả trạng thái đã/chưa cấu hình (không trả giá trị); nội dung hướng dẫn trong `knowledge/integrations/`.

## Requirements

01 §1–§8, §10–§11; 05 §6.7; ADR 0001. Lazada (connector nạp) thuộc bước 11; luồng OAuth Lazada có sẵn.

## Success Criteria

01 §12 (phần làm được không cần tài khoản sàn thật: mọi test ở 01 §11 qua).
