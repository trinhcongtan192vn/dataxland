# Feature Specification: Nền móng (khung repo, tooling, CI, compose, khách giả lập)

**Feature Branch**: `001-foundation`
**Created**: 2026-10-16
**Status**: Implemented
**Input**: `docs/specs/README.md` bước 1 (mốc M0) → `docs/specs/00-foundation.md`

Mọi yêu cầu dưới đây suy ra từ `docs/specs/00-foundation.md` (viết tắt 00). Không có yêu cầu mới.

## User Scenarios & Testing

### User Story 1 – Engineer dựng máy mới và chạy được toàn bộ test (Priority: P1)

Engineer clone repo, chạy `make setup && make up && make seed-local && make test` và mọi thứ chạy (00 §11).

**Acceptance Scenarios**:

1. **Given** máy mới, **When** chạy `make setup`, **Then** `uv sync`, `pnpm install`, `dbt deps` chạy và `.env` được tạo từ `.env.example` (00 §6).
2. **Given** stack đã bật, **When** chạy `make seed-local`, **Then** dữ liệu mẫu nạp vào dataset của `demo_seller`, `demo_agency` trên DuckDB và giá vốn, ngân sách mẫu vào Postgres (00 §5).

### User Story 2 – Dữ liệu mẫu ổn định (Priority: P1)

`ops/gen_samples.py` sinh dữ liệu mẫu với seed cố định; chạy lại cho kết quả giống hệt (00 §5, §11).

**Acceptance Scenarios**:

1. **Given** `transform/samples/`, **When** chạy lại `ops/gen_samples.py`, **Then** mọi file giống hệt từng byte.
2. Mỗi nguồn bán có ≥ 60 ngày, ≥ 200 đơn, có đơn hủy, đơn hoàn, đơn đổi trạng thái sau khi giao, một SKU lỗ sau phí, một SKU chưa có giá vốn (00 §5); có một đơn USD, ngày cuối tuần không có tỷ giá, trạng thái lạ chỉ có trong file ghi đè của `demo_seller`, SKU đổi giá vốn giữa kỳ (02 §8).

### User Story 3 – CI chạy đủ bước trên mọi PR (Priority: P1)

`.github/workflows/ci.yml` chạy 8 bước ở 00 §8.1; gitleaks; triển khai prod cần duyệt tay (00 §8.2).

### Edge Cases

- File cấu hình khách lỗi không làm hỏng khách khác (04 §1.3) – kiểm bằng `test_tenant_rules`.
- Trường có tên chứa `token|key|password|secret` ngoài `secret_ref` bị từ chối (04 §1.1).

## Requirements

- **FR-001** (00 §1): cây thư mục monorepo; thư mục chưa dùng ở GĐ1 có `README.md` một dòng.
- **FR-002** (00 §1.1): `libs/dx_common` gồm `config`, `logging`, `tenants`, `events`, `db`, `secrets`, `money`, `timeutil`.
- **FR-003** (00 §2): phiên bản ghim trong `uv.lock`, `pnpm-lock.yaml`, `transform/packages.yml`, tag image compose.
- **FR-004** (00 §4.1): `.env.example` có đủ biến.
- **FR-005** (00 §5): `tenants/demo_seller.yml`, `tenants/demo_agency.yml`, `ops/gen_samples.py`, `make seed-local`.
- **FR-006** (00 §6): Makefile có các lệnh `setup`, `up`, `down`, `seed-local`, `dbt-build`, `semantic`, `test`, `lint`, `e2e`.
- **FR-007** (00 §7): `infra/compose/docker-compose.yml` có đủ service.
- **FR-008** (00 §8): CI, triển khai, sao lưu.

## Success Criteria

- **SC-001** (00 §11): `make setup && make up && make seed-local && make test` chạy thành công trên máy mới.
- **SC-002**: CI chạy đủ các bước 00 §8.1 trên một PR rỗng.
- **SC-003**: `.env.example` đủ biến 00 §4.1.
- **SC-004**: dữ liệu mẫu sinh lại giống hệt.
