# Runbook – Cấp quyền API sàn (FR-ING-01..03, FR-ING-08, spec 01 §2.3, spec 05 §6.7)

Hướng dẫn có hình: `/ops/integrations/shopee`, `/ops/integrations/tiktok_shop`, `/ops/integrations/lazada`.

1. Khóa ứng dụng đối tác của DataxLand nằm ở secret dùng chung `dx-<source>-app`
   (JSON `{"partner_id": "...", "partner_key": "..."}` hoặc `{"app_key": "...", "app_secret": "..."}`).
2. Vào `/ops/tenants/<id>`, bấm "Kết nối" ở nguồn sàn. Cổng chuyển sang trang cấp quyền của sàn; chủ shop đăng nhập
   và đồng ý. Sàn gọi lại `/v1/connect/<source>/callback`; API ghi token vào secret
   `dx-<tenant_id>-<source>-<account_id>` và cập nhật trạng thái nguồn.
3. Thêm `secret_ref: dx-<tenant_id>-<source>-<account_id>` vào nguồn trong `tenants/<id>.yml`, mở PR.
4. Token tự làm mới trước mỗi lần chạy. Khi quyền bị thu hồi, pipeline phát `sync.failed` với `reason: auth_revoked`:
   làm lại bước 2.
