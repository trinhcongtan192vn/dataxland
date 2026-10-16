# Tasks: Nền móng

**Input**: [spec.md](spec.md), [plan.md](plan.md)

## Phase 1: Setup

- [x] T001 `pyproject.toml` gốc (uv workspace), `.python-version`, cấu hình ruff/mypy/pytest
- [x] T002 [P] `package.json`, `pnpm-workspace.yaml`, khung `apps/web` (Next.js, Tailwind, eslint, prettier, vitest)
- [x] T003 [P] `.gitignore`, `.gitattributes`, `.gitleaks.toml`, `.env.example` (00 §4.1)

## Phase 2: Foundational

- [x] T004 `libs/dx_common`: `config`, `logging`, `ids`, `timeutil`, `money`, `db`, `secrets`, `testing`
- [x] T005 `dx_common.tenants`: model, mặc định theo gói, `validate`, CLI `python -m dx_common.tenants validate`
- [x] T006 `dx_common.events`: bảng outbox, schema payload, `publish`, `consume` (idempotent, dead letter)

## Phase 3: US1/US2 – Khách giả lập và dữ liệu mẫu

- [x] T007 `tenants/demo_seller.yml`, `tenants/demo_agency.yml`, `tenants/partners.yml`, file ghi đè
- [x] T008 `ops/gen_samples.py` (seed cố định) → `transform/samples/`
- [x] T009 `ops/seed_local.py`, `ops/init_local.py`
- [x] T010 Test: `test_common.py`, `test_events.py`, `apps/web/lib/format.test.ts`

## Phase 4: US3 – Compose, CI, triển khai

- [x] T011 `infra/compose/docker-compose.yml`, Dockerfile từng dịch vụ, Caddyfile, Firebase emulator
- [x] T012 `.github/workflows/ci.yml` (8 bước 00 §8.1), `deploy.yml` (00 §8.2)
- [x] T013 `Makefile` (00 §6)
- [x] T014 `ops/backup_postgres.sh`, `ops/runbooks/restore-log.md` (00 §8.3)
