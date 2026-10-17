# Implementation Plan: Lazada, xóa dữ liệu người mua

**Branch**: `011-lazada-erasure` | **Spec**: [spec.md](spec.md)

- `pipelines/connectors/lazada/`: client (ký, làm mới token, mã lỗi), resources (6 bảng), source, README, test respx.
- `transform/pii_columns.yml`, `ops/erase_subject.py`; test `transform/tests/test_erase_subject.py` chạy dbt thật.
- Nhóm Telegram, giới hạn tần suất: xem `specs/008-weekly-report-bot`.

Quyết định: ADR 0002 #40–#41.
