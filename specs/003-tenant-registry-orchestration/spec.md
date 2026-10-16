# Feature Specification: Sổ đăng ký khách, sự kiện, điều phối, thông báo

**Feature Branch**: `003-tenant-registry-orchestration`
**Created**: 2026-10-16
**Status**: Implemented
**Input**: `docs/specs/README.md` bước 3 (M0) → `docs/specs/04-ops-and-orchestration.md` (viết tắt 04)

## User Scenarios & Testing

### US1 – Data lead thêm khách bằng cấu hình (P1)

1. Sửa `tenants/<id>.yml`, merge → trong 5 phút API trả cấu hình mới (FR-OPS-01, 04 §1.3). File lỗi không làm hỏng khách khác.
2. `ops/bootstrap_tenant.py` chạy lại không tạo trùng (FR-OPS-02, 04 §2).

### US2 – Pipeline theo khách dừng đúng chỗ khi lỗi (P1)

1. Bước lỗi → các bước sau không chạy, phát `sync.failed` với `reason` (FR-OPS-03, 04 §3.2).
2. Test chặn → không hoán đổi marts, không làm mới Cube, không phát `transform.finished`, phát `test.failed` (FR-DQ-04).
3. Lịch đồng bộ và báo cáo tuần đọc từ cấu hình; đổi cron không cần sửa code (FR-ING-06, 04 §3.3).

### US3 – Team và khách nhận thông báo qua kênh độc lập (P1)

1. `sync.failed`, `test.failed` → nhóm Telegram nội bộ và email team trong một vòng worker (FR-OPS-05).
2. Thêm adapter kênh mới không sửa `dispatcher.py` (FR-OPS-08).
3. Telegram lỗi → email vẫn gửi; lỗi kết nối 30 phút → báo team qua email (NFR-12, 04 §5.4).

## Requirements

- **FR-001** (04 §1): `dx_common.tenants`, `ops/sync_tenants.py`, `tenants/partners.yml`.
- **FR-002** (04 §2): `ops/bootstrap_tenant.py` (local: DuckDB + `.secrets/`; dev/prod: `bq`, `gcloud`).
- **FR-003** (04 §3): Dagster code location: partition động `tenants`, `tenant_pipeline`, `weekly_report`, job cố định, sensor `tenant_partitions`, `tenant_schedule`, `events`.
- **FR-004** (04 §4): outbox `events` (đã có ở 001).
- **FR-005** (04 §5): trung tâm thông báo, mẫu có phiên bản, worker `python -m app.workers`.
- **FR-006** (04 §6): `pipeline_runs`, `source_syncs`, `GET /v1/ops/overview`.
- **FR-007** (04 §9): runbook bắt buộc.

## Success Criteria (04 §11)

- Hai khách giả lập chạy `tenant_pipeline` theo lịch trên `local` (cần dbt ở feature 004, Cube ở 005).
- Mọi test 04 §10 qua: `test_fr_ops_01_sync_tenants`, `test_fr_ops_02_bootstrap_idempotent`, `test_fr_ops_03_step_failure_stops_pipeline`, `test_fr_dq_04_blocked_run_does_not_swap_or_refresh` (phần điều phối; phần dbt ở 004), `test_fr_ing_06_schedule_from_config`, `test_fr_ops_05_team_alert_within_window`, `test_fr_ops_08_fake_channel_adapter`, `test_nfr_12_email_sent_when_telegram_down`, `test_events_idempotent_consumer`. `test_fr_ops_09_erase_subject` ở feature 011.
