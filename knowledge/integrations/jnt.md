# J&T Express (file đối soát)

J&T Express chưa có API công khai cho đơn của shop, nên DataxLand nạp vận đơn từ **file đối soát** khách tải lên
(FR-ING-09, ADR 0005). Không cần khóa hay secret.

## 1. Bật nguồn

Thêm vào `tenants/<tenant_id>.yml` qua PR:

```yaml
  - type: jnt
    connector: dlt
    account_id: file
```

## 2. Xuất file đối soát

1. Đăng nhập **jtexpress.vn → Khách hàng (VIP/Đối tác)**.
2. Mở **Đối soát → Bảng kê đối soát COD** (hoặc **Quản lý vận đơn → Xuất Excel**), chọn khoảng ngày, xuất **Excel**.
3. File cần các cột: **Mã vận đơn**, **Mã đơn hàng**, **Trạng thái**, **Phí vận chuyển**, **Tiền COD**, **Ngày gửi**.
   Cột **Phí hoàn**, **Phí bảo hiểm**, **Trọng lượng** nếu có cũng được đọc. Cột tên, số điện thoại, địa chỉ người
   nhận bị bỏ qua.

## 3. Tải lên

Trên cổng DataxLand: **Nhập liệu → Vận chuyển → Tải file J&T**. File được nạp ở lần chạy dữ liệu kế tiếp (khoảng
10–20 phút); bảng file hiện "Đã nạp N vận đơn" hoặc lý do bị từ chối. Tải lại file trùng vận đơn thì số mới thay số cũ.
