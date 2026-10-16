# Tỷ giá Vietcombank

Tỷ giá dùng để quy đổi doanh thu và chi phí bằng ngoại tệ (Amazon, quảng cáo tính bằng USD) về VND (FR-MOD-03, spec 01 §6).

- Nguồn: dữ liệu tỷ giá công khai của Vietcombank, không cần khóa.
- `FX_VCB_URL`: mặc định `https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx`. Đổi nếu Vietcombank đổi địa chỉ.
- `FX_CURRENCIES`: danh sách mã ngoại tệ, cách nhau bởi dấu phẩy, mặc định `USD`.
- Job `fx_daily` chạy 18:30 giờ Việt Nam, lấy cột **Bán ra**, ghi vào `dx_ref.fx_rates`.

## Khi lấy tỷ giá lỗi

- Team nhận cảnh báo `sync.failed` (nguồn `fx_vcb`).
- Nhập tay: **Vận hành → Tỷ giá → Thêm** (gọi `POST /v1/admin/fx-rates`). Tỷ giá nhập tay được ưu tiên hơn tỷ giá tự động cùng ngày.
- Ngày không có tỷ giá (cuối tuần, lễ) tự lấy tỷ giá của ngày làm việc gần nhất trước đó.
