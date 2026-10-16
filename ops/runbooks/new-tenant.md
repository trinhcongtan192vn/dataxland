# Runbook – Thiết lập khách mới (J2, spec 04 §2, §8.5)

1. Viết `tenants/<tenant_id>.yml` theo `docs/specs/04-ops-and-orchestration.md` §1.1 (hoặc lấy bản nháp từ lượt kiểm tra
   sức khỏe: `/ops/health-checks/<id>` → "Chuyển thành khách"). Mở pull request; CI chạy
   `python -m dx_common.tenants validate tenants/`.
2. Merge. Trong 5 phút `sync_tenants` đưa cấu hình vào Postgres và báo team "Khách mới cần chạy bootstrap".
3. Chạy bootstrap (chạy lại không tạo trùng):
   ```bash
   uv run python ops/bootstrap_tenant.py <tenant_id> --env prod
   ```
4. Làm theo checklist in ra:
   - Kết nối Windsor cho từng nguồn quảng cáo: `windsor-setup.md`, hướng dẫn trên cổng `/ops/integrations/windsor`.
   - Cấp quyền OAuth cho từng sàn: `marketplace-oauth.md`, hướng dẫn `/ops/integrations/<sàn>`.
   - Tạo secret còn thiếu (tên in trong checklist).
   - Mời owner: `/ops/tenants/<id>` → "Mời owner" (hoặc `POST /v1/members/invitations` với `role: owner`).
5. `tenant.created` mở lần chạy đầu: nạp 90 ngày lịch sử, chạy toàn bộ test và đối soát. Theo dõi ở `/ops`.
6. Owner nhập giá vốn (`/app/inputs/costs`), liên kết Telegram (`/app/settings/telegram`).
7. Rà số với khách, sửa ánh xạ nếu cần (`tenants/overrides/<id>_status_map.csv`), rồi dựng báo cáo đầu tiên từ `/ops/reports`.
8. Buổi bàn giao: đi qua sổ tay chỉ số và báo cáo đầu tiên.
