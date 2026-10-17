# Implementation Plan: Màn hình vận hành và trang agency

**Branch**: `010-ops-agency` | **Spec**: [spec.md](spec.md)

- API: `GET /v1/partner/tenants` (mỗi khách một `AuthContext`, lỗi một khách không làm hỏng trang).
- Web: `/ops`, `/ops/tenants/[id]`, `/ops/integrations[/key]`, `/ops/fx-rates`, `/partner`, `/partner/[tenant]`.
- `ops/seed_users.py` trong `make seed-local`; `apps/web/e2e/*.spec.ts`, `playwright.config.ts`.

Quyết định: ADR 0002 #37–#39.
