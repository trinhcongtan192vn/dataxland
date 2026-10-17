# Giao Hàng Nhanh (GHN)

DataxLand lấy phí vận chuyển, phí hoàn, COD và trạng thái theo vận đơn GHN (FR-ING-09). GHN không có API liệt kê đơn
của shop, nên DataxLand nhận mã vận đơn qua **webhook** rồi gọi API chi tiết vận đơn để lấy phí.

## 1. Lấy Token và ShopId

1. Đăng nhập **khachhang.ghn.vn** bằng tài khoản chủ shop.
2. Mở **Chủ cửa hàng → Xem thông tin → API Token**, bấm **Xem** để lấy **Token**.
3. Ở **Quản lý cửa hàng**, ghi lại **ShopId** của cửa hàng gửi hàng.

## 2. Ghi khóa

Secret `dx-<tenant_id>-ghn-<ShopId>` (Secret Manager ở dev/prod, `.secrets/` ở local), nội dung JSON:

```json
{"token": "<Token>", "shop_id": "<ShopId>"}
```

Thêm nguồn vào `tenants/<tenant_id>.yml` qua PR:

```yaml
  - type: ghn
    connector: dlt
    account_id: "<ShopId>"
    secret_ref: dx-<tenant_id>-ghn-<ShopId>
```

## 3. Cài webhook

1. Trên cổng DataxLand, chủ shop mở **Nhập liệu → Vận chuyển**, sao chép **URL webhook GHN**.
2. Trên **khachhang.ghn.vn → Cài đặt → Cấu hình webhook (Callback URL)**, dán URL và lưu.
3. Từ lúc này mỗi lần GHN đổi trạng thái vận đơn, DataxLand nhận được mã vận đơn. Vận đơn tạo trước khi cài webhook
   không được nạp.

DataxLand chỉ lưu trường vận đơn; tên, số điện thoại, địa chỉ người nhận trong webhook bị bỏ ngay.

## 4. Kiểm tra

- Màn **Vận chuyển** hiện số vận đơn đã nhận và thời điểm gần nhất.
- Sau lần chạy kế tiếp, chỉ số **Phí hãng vận chuyển**, **Tiền thu hộ (COD)**, **Số vận đơn** có số.
- Môi trường thử của GHN: `https://dev-online-gateway.ghn.vn` (tài liệu: developer.ghn.vn).
