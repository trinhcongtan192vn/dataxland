# Feature Specification: Control plane, xác thực và phân quyền

**Feature Branch**: `002-control-plane-auth`
**Created**: 2026-10-16
**Status**: Implemented
**Input**: `docs/specs/README.md` bước 2 (M0) → `docs/specs/05-api-and-auth.md` (viết tắt 05)

## User Scenarios & Testing

### US1 – Người dùng đăng nhập và chỉ thấy khách của mình (P1)

1. **Given** token Firebase hợp lệ, **When** gọi `GET /v1/me`, **Then** nhận người dùng, khách và vai trò (05 §6.1). Token sai, hết hạn, bị thu hồi → 401 (FR-AUTH-01).
2. **Given** người dùng của `demo_seller`, **When** gọi với `X-Tenant-Id: demo_agency`, **Then** `403 TENANT_FORBIDDEN` (NFR-01, 00 §9.1).
3. **Given** người dùng thuộc nhiều khách và không gửi `X-Tenant-Id`, **Then** `400 TENANT_REQUIRED` (05 §3.2).

### US2 – Ma trận quyền (P1)

Mọi ô của bảng 05 §4 đúng như spec (FR-AUTH-02).

### US3 – Owner quản lý thành viên và agency (P1)

1. Owner mời member với danh sách chỉ số; gỡ member thì gỡ luôn liên kết Telegram (FR-AUTH-03, 05 §5.1). Không gỡ được owner duy nhất (`409 LAST_OWNER`).
2. Owner cấp và thu quyền agency; thu quyền có hiệu lực ở lần gọi kế tiếp và gỡ liên kết Telegram của agency (FR-AUTH-04, 05 §5.3).

### US4 – Nhập giá vốn và ngân sách (P1)

1. Giá vốn có ngày hiệu lực; `valid_to` tính từ bản kế tiếp (FR-INP-01).
2. File Excel: dòng lỗi báo rõ dòng, cột, lý do; dòng hợp lệ vẫn nhận (FR-INP-02, 05 §6.4).
3. Ngân sách: nền tảng khách không có → 400 (FR-INP-04).

### Edge Cases

- Token nội bộ gọi endpoint người dùng → 403; token người dùng gọi `/v1/internal/*` → 403 (NFR-02).
- File cấu hình khách lỗi không làm hỏng khách khác khi đồng bộ (FR-OPS-01, 04 §1.3).

## Requirements

- **FR-001** (05 §2): Alembic tạo đủ bảng 05 §2.1–2.3.
- **FR-002** (05 §3): xác thực Firebase, `AuthContext` đọc quyền từ Postgres ở mỗi request, custom claims chỉ cho giao diện.
- **FR-003** (05 §4): `permissions.py` và `require(ctx, action)`.
- **FR-004** (05 §5, §6.1, §6.3–6.5): endpoint `me`, `tenants`, `members`, `partners`, `inputs`.
- **FR-005** (05 §7): `audit_log` cho các hành động liệt kê.
- **FR-006** (05 §8): giới hạn 120/phút, 30/phút cho `POST /v1/metrics/query`.
- **FR-007** (00 §3.4): lỗi RFC 9457, `X-Request-Id`.

## Success Criteria (05 §10)

- `alembic upgrade head` tạo đủ bảng trên Postgres trống.
- OpenAPI tại `/openapi.json`; `pnpm gen:api` sinh client TypeScript.
- Mọi test ở 05 §9 qua (một số test cần bộ máy chỉ số được hoàn thiện ở feature 005).
