# Implementation Plan: Lớp chỉ số

**Branch**: `005-semantic-layer` | **Spec**: [spec.md](spec.md) | **Nguồn**: `docs/specs/03-semantic-layer.md`

## Technical Context

- Thư viện YAML trong `semantic/metrics/{common,seller,agency}`, `dimensions.yml`, `sources.yml`.
- `semantic/build.py` (Python, PyYAML): kiểm tra schema, tham chiếu, vòng lặp, chiều theo mart; sinh `semantic/cube/model/*.yml` và `semantic/dist/*`.
- Cube 1.7.50 (`cube/cube.js`): JWT HS256, `securityContext {tenant_id, dataset_prefix}`, `COMPILE_CONTEXT` chọn dataset; driver BigQuery (dev/prod), DuckDB chỉ đọc (local, ADR 0002 #20).
- Bộ máy trong `services/api/app/metrics`: `registry` (đọc `metrics.json`), `periods`, `cube_client`, `expr` (công thức an toàn), `engine` (phân rã chỉ số tổng hợp qua nhiều cube, so kỳ, cảnh báo, nhật ký `metric_queries`), `key_numbers`, `flags`, `anomaly`.
- Router `services/api/app/routers/metrics.py`; `POST /v1/internal/anomalies/run` cho Dagster sau khi làm mới Cube.

## Constitution Check

- Một định nghĩa chỉ số: web/bot/báo cáo chỉ gọi API (nguyên tắc II).
- Tách biệt khách: khách lấy từ quyền người gọi; Cube kiểm `dataset_prefix` khớp `tenant_id` (nguyên tắc III).
- Không sửa tay `semantic/cube`, `semantic/dist`: CI chạy `build.py` + `git diff --exit-code`.

## Quyết định cài đặt

ADR 0002 #18–#22.
