# Runbook – Yêu cầu của chủ thể dữ liệu (FR-OPS-09, NFR-11, spec 04 §8)

Khách (bên kiểm soát) chuyển yêu cầu xem, sửa, xóa dữ liệu của một người mua cho DataxLand (bên xử lý).

1. Ghi nhận yêu cầu: ngày nhận, khách, kênh nhận, hạn trả lời theo Luật 91/2025/QH15 và hợp đồng xử lý dữ liệu.
2. Xác minh yêu cầu đến từ khách (owner) qua kênh đã đăng ký.
3. Đếm trước:
   ```bash
   uv run python ops/erase_subject.py --tenant <id> --phone <số> --dry-run
   ```
4. Xóa:
   ```bash
   uv run python ops/erase_subject.py --tenant <id> --phone <số>
   ```
   Script xóa thông tin cá nhân trong `raw` (giữ đơn để không sai doanh thu), chạy lại dbt `--full-refresh` cho model có
   thông tin người mua, và ghi `erasure_log` (chỉ lưu giá trị băm).
5. Xác nhận với khách bằng email, nêu ngày hoàn tất và số bản ghi bị ảnh hưởng.
