# Implementation Plan: Control plane, xác thực và phân quyền

**Branch**: `002-control-plane-auth` | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

## Technical Context

- FastAPI, SQLAlchemy 2 (Declarative, `Mapped`), Alembic, psycopg 3, firebase-admin, openpyxl, Jinja2.
- Test: pytest + `TestClient`; Postgres tạm chạy `alembic upgrade head` một lần cho cả phiên; Firebase giả (`uid:<id>`).

## Constitution Check

| Nguyên tắc | Kết quả |
|---|---|
| I | Mọi endpoint, bảng, mã lỗi lấy từ 05; bảng phụ cần cho cài đặt (`notification_groups`, `channel_health`, `metric_anomalies`, `rate_counters`) ghi trong ADR 0002 |
| II | `tenant_id` chỉ lấy từ header rồi đối chiếu quyền trong Postgres ở mỗi request (05 §3.2); không cache |
| III | Không có SQL chỉ số ở API; endpoint SKU thiếu giá vốn gọi bộ máy chỉ số |
| IV | Không bảng nào chứa PII người mua; log có bộ lọc che; không trả `secret_ref` |
| VI | Test đặt tên theo mã FR |

## Structure

`services/api/app/{main.py, errors.py, audit.py, ratelimit.py, claims.py, registry_sync.py}`, `auth/`, `db/`, `routers/`, `inputs/`, `notify/`, `telegram/`, `metrics/registry.py`; `alembic/versions/0001_initial_schema.py`.
