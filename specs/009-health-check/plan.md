# Implementation Plan: Kiểm tra sức khỏe dữ liệu

**Branch**: `009-health-check` | **Spec**: [spec.md](spec.md)

## Technical Context

- `pipelines/connectors/files/`: `signatures.yml` (nhận diện ≥ 80% cột), `readers.py` (xlsx read_only, csv tự nhận mã hóa/dấu phân cách, số và ngày kiểu Việt Nam), `adapters/` (Shopee, TikTok Shop, Lazada, quảng cáo, giá vốn), `source.py` (`load_files`).
- `transform/macros/dx_file_staging.sql` + model `stg_*_file__*` (orders, order_lines, fees, returns, products, ad_insights_daily) và `stg_portal_file__product_costs`.
- Job `healthcheck` (tạo bảng ghi đè và identity rỗng, loại unit test), `healthcheck_cleanup`, `healthcheck_convert`.
- API: `app/healthchecks/{tenant,result}.py`, router `health_checks` (công khai, vận hành, nội bộ), văn bản đồng ý `knowledge/legal/health-check-consent.md`.
- Web: `/health-check`, `/health-check/verify`, `/health-check/[id]`, `/ops/health-checks`, `/ops/health-checks/[id]`.

## Quyết định

ADR 0002 #32–#36.
