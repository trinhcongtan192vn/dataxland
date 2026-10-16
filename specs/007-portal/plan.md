# Implementation Plan: Cổng khách hàng

**Branch**: `007-portal` | **Spec**: [spec.md](spec.md)

## Technical Context

- Next.js 15 App Router (client components), TanStack Query, Recharts, TanStack Table, Firebase JS SDK.
- `lib/api/schema.d.ts` sinh từ OpenAPI (`pnpm --filter web gen:api` → `services/api/scripts/dump_openapi.py` + `openapi-typescript`); client `openapi-fetch` gắn ID token và `X-Tenant-Id`.
- `lib/tenant.ts`: khách trong `?t=`, `useMe`, `useUrlState` cho bộ lọc.
- Component: `app-shell`, `block` (tải/lỗi/CSV từng khối), `charts`, `tables/data-table`, `filter-bar`, `data-status`, `metric-label`, `key-numbers`, `stat-cards`, `flags`, `agency-dashboard` (dùng lại cho trang agency ở bước 10).
- API: router `decisions` (05/06 §7.3) và `POST /v1/internal/decisions/remind` cho job `decision_reminders`.

## Constitution Check

- Web chỉ gọi `services/api`; số đi qua `POST /v1/metrics/query`. Phần web tự làm chỉ là định dạng và so sánh hai giá trị API trả về để hiển thị (thay đổi %, tỷ lệ phí trên doanh thu, vạch tiến độ).
- Quyền: menu theo `permissions` của `/v1/me`; backend vẫn chặn.

## Quyết định

ADR 0004 (Accepted): bỏ `hidden` cho `allocated_ad_spend`, `budget`, `spend_mtd`.
