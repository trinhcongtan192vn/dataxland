# Connector tỷ giá Vietcombank

- Nguồn: XML công khai `FX_VCB_URL` (mặc định `portal.vietcombank.com.vn/.../pXML.aspx`), phần tử `Exrate` với `Buy`, `Transfer`, `Sell`.
- Lấy `Sell` (bán ra). Đọc XML bằng `defusedxml`.
- Ghi `merge` vào `dx_ref.fx_rates` theo (`date`, `currency`, `source`), kèm tỷ giá nhập tay (`source = manual`).
- Job `fx_daily`, 18:30 giờ Việt Nam. Lỗi → `sync.failed` (`tenant_id = null`, `source = fx_vcb`).
