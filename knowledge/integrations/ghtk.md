# Giao Hàng Tiết Kiệm (GHTK)

DataxLand lấy phí vận chuyển, phí bảo hiểm, COD và trạng thái theo vận đơn GHTK (FR-ING-09). GHTK chỉ có API tra cứu
theo mã vận đơn, nên DataxLand nhận mã vận đơn qua **webhook** rồi gọi API trạng thái để lấy phí.

## 1. Lấy Token API

1. Đăng nhập **khachhang.giaohangtietkiem.vn** bằng tài khoản chủ shop.
2. Mở **Cài đặt → Cấu hình API** (bản cũ: **Thông tin tài khoản → Token API**), tạo token có quyền **xem trạng thái
   đơn hàng**.
3. Nếu GHTK cấp **mã đối tác** (`X-Client-Source`), ghi lại; không có thì để trống.

## 2. Ghi khóa

Secret `dx-<tenant_id>-ghtk-<mã shop>`, nội dung JSON:

```json
{"token": "<Token>", "partner_code": "<mã đối tác hoặc rỗng>"}
```

Thêm nguồn vào `tenants/<tenant_id>.yml` qua PR:

```yaml
  - type: ghtk
    connector: dlt
    account_id: "<mã shop>"
    secret_ref: dx-<tenant_id>-ghtk-<mã shop>
```

## 3. Cài webhook

1. Trên cổng DataxLand, chủ shop mở **Nhập liệu → Vận chuyển**, sao chép **URL webhook GHTK**.
2. Gửi URL cho GHTK qua trang **Cấu hình API → Webhook URL** (hoặc nhờ nhân viên hỗ trợ GHTK khai báo).
3. Vận đơn tạo trước khi cài webhook không được nạp.

Tài liệu GHTK: api.ghtk.vn/docs/submit-order/tracking-status và .../webhook.
