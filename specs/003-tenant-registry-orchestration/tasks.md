# Tasks: Sổ đăng ký, điều phối, thông báo

- [x] T001 `app/registry_sync.py`, `ops/sync_tenants.py` – `test_fr_ops_01_sync_tenants`
- [x] T002 `ops/bootstrap_tenant.py` – `test_fr_ops_02_bootstrap_idempotent`
- [x] T003 Adapter kho dữ liệu `pipelines/dx_pipelines/warehouse.py` (DuckDB, BigQuery có nhãn `tenant_id`)
- [x] T004 Runner `tenant_pipeline` – `test_fr_ops_03_step_failure_stops_pipeline`, `test_fr_dq_04_blocked_run_does_not_swap_or_refresh`
- [x] T005 Connector khung, `portal`, dữ liệu mẫu local; nạp file ghi đè
- [x] T006 Dagster: partition, job, sensor, lịch cố định – `test_fr_ing_06_schedule_from_config`, `test_inputs_changed_debounced_10_minutes`
- [x] T007 Trung tâm thông báo, worker – `test_fr_ops_05_*`, `test_fr_ops_08_*`, `test_nfr_12_*`
- [x] T008 `GET /v1/ops/overview`, lịch sử chạy, chạy lại, tỷ giá tay – `test_fr_ops_04_overview_reflects_runs`
- [x] T009 Runbook `ops/runbooks/*.md`
