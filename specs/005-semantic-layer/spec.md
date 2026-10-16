# Feature Specification: Lớp chỉ số (Semantic layer)

**Feature Branch**: `005-semantic-layer`
**Created**: 2026-10-16
**Status**: Implemented
**Input**: `docs/specs/README.md` bước 5 (M0) → `docs/specs/03-semantic-layer.md` (viết tắt 03)

## User Scenarios & Testing

### US1 – Một định nghĩa chỉ số, sinh ra mọi thứ (P1)

Data lead sửa `semantic/metrics/*.yml`, chạy `make semantic`; `build.py` kiểm tra rồi sinh model Cube, `metrics.json`, `handbook.json`, `ai_context.md` (FR-MET-01, FR-MET-02).

**Acceptance**: YAML sai báo lỗi rõ kèm tên file; chạy hai lần cho kết quả giống hệt; CI báo lỗi khi file sinh ra lệch.

### US2 – Mọi số đi qua `POST /v1/metrics/query` (P1)

Cổng, bot, báo cáo gọi một endpoint; phản hồi có `version`, `data_as_of`, cảnh báo `MISSING_COGS`, `PROVISIONAL`, `STALE` (FR-MET-05, FR-MET-06, FR-INP-03).

**Acceptance**: Cube từ chối JWT thiếu `tenant_id`; cùng truy vấn với hai khách đọc đúng dataset của từng khách; member chỉ thấy chỉ số trong allowlist (FR-AUTH-03).

### US3 – Ba số chính, cờ cần chú ý, bất thường (P1)

`GET /v1/metrics/key-numbers`, `GET /v1/metrics/flags` (FR-AGY-01); phát `metric.anomaly` khi lệch quá ngưỡng so với trung bình 4 kỳ, mỗi kỳ một lần (FR-MET-07).

### US4 – Phiên bản chỉ số (P2)

`check_versions.py` chặn đổi công thức mà không tăng `version`; `ops/release_metrics.py` phát `metric.released` sau triển khai (FR-MET-08).

## Requirements

FR-MET-01..08, FR-INP-03, FR-AGY-01, NFR-04, NFR-10 theo 03 §2–§10. Không thêm yêu cầu ngoài 03.

## Success Criteria

03 §12.
