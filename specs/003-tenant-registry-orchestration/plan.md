# Implementation Plan: Sổ đăng ký, điều phối, thông báo

**Branch**: `003-tenant-registry-orchestration` | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

## Summary

- Các bước của `tenant_pipeline` viết thành runner Python thuần (`pipelines/dx_pipelines/runner.py`) để test được với
  dịch vụ giả; job Dagster chỉ bọc runner (một op, log từng bước).
- Dagster gọi `services/api` qua token nội bộ cho trạng thái chạy, sự kiện, bất thường, báo cáo (không đọc thẳng DB của API),
  trừ sensor sự kiện đọc outbox qua `dx_common.events.consume` như spec 04 §4.2 quy định.
- Trung tâm thông báo trong `services/api/app/notify/` chạy ở worker nền.

## Constitution Check

| Nguyên tắc | Kết quả |
|---|---|
| I | Mọi bước, sự kiện, lý do lỗi theo 04; sự kiện nội bộ thêm ghi ở ADR 0002 #11 |
| II | Mỗi lần chạy dùng tài khoản dịch vụ của khách (`get_warehouse(tenant_id)`); mỗi khách một partition, giới hạn 1 lần chạy |
| IV | Mẫu tin không có biến PII (`test_fr_tg_08_no_buyer_pii_in_templates`); log chỉ ghi số dòng, mã lỗi |
| VI | Test theo mã FR |

## Quyết định cài đặt

- Ở `local`, nguồn sàn chưa có secret dùng adapter dữ liệu mẫu (`connectors/samples.py`) – chỉ là chọn adapter theo môi trường (00 §4).
- Nguồn `portal` ghi ảnh chụp đầy đủ bảng Postgres của khách vào raw qua adapter kho dữ liệu (không cần dlt cho hai bảng nhỏ).
- Marts dựng vào bảng `__staging`, bước `swap_marts` gọi macro `dx_swap_marts()` (02 §6.3).
