# Tasks: Control plane, xác thực và phân quyền

- [x] T001 SQLAlchemy models cho mọi bảng 05 §2 (`app/db/models.py`) và migration `0001_initial_schema`
- [x] T002 Lỗi RFC 9457, middleware `X-Request-Id`, log JSON (`app/errors.py`, `app/main.py`)
- [x] T003 Xác thực Firebase và Firebase giả cho test (`app/auth/firebase.py`)
- [x] T004 `AuthContext`, `get_ctx`, `build_ctx`, `bot_ctx_for_link`, `internal_ctx` (`app/auth/context.py`)
- [x] T005 Ma trận quyền (`app/auth/permissions.py`) – `test_fr_auth_02_permission_matrix_cells`
- [x] T006 Xác thực dịch vụ nội bộ (`app/auth/internal.py`) – `test_internal_endpoints_reject_user_token`
- [x] T007 `GET /v1/me`, `GET /v1/tenants/{id}`
- [x] T008 Thành viên, lời mời (`routers/members.py`) – `test_members_last_owner_and_removal`
- [x] T009 Cấp, thu quyền agency (`routers/partners.py`) – `test_fr_auth_04_revoke_is_immediate`
- [x] T010 Giá vốn, Excel, ngân sách (`routers/inputs.py`, `inputs/excel.py`) – `test_fr_inp_01_*`, `test_fr_inp_02_*`, `test_fr_inp_04_*`
- [x] T011 Giới hạn tần suất (`app/ratelimit.py`), nhật ký kiểm toán (`app/audit.py`)
- [x] T012 Đồng bộ sổ đăng ký (`app/registry_sync.py`, `ops/sync_tenants.py`) – `test_fr_ops_01_sync_tenants`
- [x] T013 Lớp kênh thông báo dùng chung (`app/notify/`), mẫu tin có phiên bản
- [ ] T014 (feature 005) `test_fr_auth_03_member_allowlist`, `test_fr_auth_05_no_buyer_pii_in_responses` chạy với bộ máy chỉ số
- [ ] T015 (feature 007) `pnpm gen:api`
