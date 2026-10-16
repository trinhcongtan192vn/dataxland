# Runbook – Kết thúc dịch vụ cho khách

1. Đặt `status: offboarding` trong `tenants/<id>.yml`, merge. Pipeline dừng chạy theo lịch.
2. Xuất dữ liệu cho khách nếu hợp đồng yêu cầu (bảng marts dạng CSV).
3. Thu hồi: gỡ liên kết Telegram, xóa thành viên, thu quyền agency trên cổng; xóa kết nối Windsor; thu hồi OAuth trên sàn.
4. Xóa secret `dx-<id>-*`, dataset `t_<id>_*`, tài khoản dịch vụ `dxt-<slug>`.
5. Xóa file `tenants/<id>.yml`; `sync_tenants` đặt khách thành `archived` (không xóa bản ghi để giữ nhật ký kiểm toán).
