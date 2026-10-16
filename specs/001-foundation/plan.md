# Implementation Plan: Nền móng

**Branch**: `001-foundation` | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

## Summary

Dựng monorepo theo 00 §1: uv workspace (Python 3.12), pnpm workspace (Next.js), `libs/dx_common`, cấu hình hai khách giả lập, bộ sinh dữ liệu mẫu, Makefile, Docker Compose, CI.

## Technical Context

- **Language/Version**: Python 3.12 (uv), Node 22 (pnpm), TypeScript strict.
- **Primary Dependencies**: pydantic-settings, SQLAlchemy 2, psycopg 3, python-ulid, croniter (dx_common); Next.js 15, Tailwind 3 (web).
- **Storage**: Postgres 16 (control plane), DuckDB (local), BigQuery (dev/prod).
- **Testing**: pytest (+ Postgres tạm: `DX_TEST_DATABASE_URL` trong CI, `pgserver` nhúng trên máy không có Docker), vitest.
- **Target Platform**: Linux container (VM GĐ1); máy dev Windows/macOS/Linux.

## Constitution Check

| Nguyên tắc | Kết quả |
|---|---|
| I. Nguồn sự thật | Mọi mục truy về 00; chi tiết tự quyết ghi ở `docs/adr/0002-*.md` |
| II. Tách biệt khách | `tenant_id` kiểm theo quy ước; dataset theo tiền tố khách |
| III. Một định nghĩa chỉ số | Không áp dụng ở bước này |
| IV. PII và bí mật | `.secrets/`, `.env` trong `.gitignore`; `dx_common.secrets`; `validate` cấm khóa bí mật trong YAML; log có bộ lọc che |
| V. AI đề xuất, người duyệt | Không áp dụng |
| VI. Test theo mã yêu cầu | `libs/dx_common/tests` |

## Project Structure

Theo 00 §1 và architecture §13. Quyết định: thư viện dùng chung ở `libs/dx_common/src/dx_common`; mỗi service là một thành viên uv workspace; `ops/` chứa script chạy bằng `uv run python ops/<script>.py`.
