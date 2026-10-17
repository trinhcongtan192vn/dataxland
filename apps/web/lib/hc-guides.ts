// Hướng dẫn ngắn "Xuất file này ở đâu" cho từng loại file của kiểm tra sức khỏe (spec 07 §2).
// Ảnh chụp màn hình đặt ở `public/hc-guides/<kind>.png` khi có; thiếu ảnh thì chỉ hiện các bước.

export type HcGuide = { title: string; steps: string[]; note?: string };

export const HC_GUIDES: Record<string, HcGuide> = {
  shopee_orders: {
    title: "Shopee – Đơn hàng",
    steps: [
      "Đăng nhập Kênh Người Bán (banhang.shopee.vn) bằng tài khoản chủ shop.",
      "Vào Quản lý đơn hàng → Tất cả.",
      "Chọn khoảng thời gian (tối đa 3 tháng gần nhất), bấm Xuất.",
      "Tải file .xlsx khi Shopee báo đã xuất xong.",
    ],
  },
  shopee_income: {
    title: "Shopee – Báo cáo doanh thu",
    steps: [
      "Trong Kênh Người Bán, vào Tài chính → Doanh thu.",
      "Chọn tab Đã thanh toán, chọn cùng khoảng thời gian với file đơn hàng.",
      "Bấm Xuất và tải file .xlsx.",
    ],
  },
  tiktok_shop_orders: {
    title: "TikTok Shop – Đơn hàng",
    steps: [
      "Đăng nhập TikTok Shop Seller Center.",
      "Vào Đơn hàng → Quản lý đơn hàng, bấm Xuất.",
      "Chọn khoảng thời gian và định dạng CSV, tải về.",
    ],
  },
  tiktok_shop_settlement: {
    title: "TikTok Shop – Báo cáo quyết toán",
    steps: [
      "Trong Seller Center, vào Tài chính → Quyết toán (Settlements).",
      "Chọn khoảng thời gian, bấm Xuất báo cáo theo đơn.",
    ],
  },
  lazada_orders: {
    title: "Lazada – Đơn hàng",
    steps: [
      "Đăng nhập Lazada Seller Center.",
      "Vào Đơn hàng → Quản lý đơn hàng, chọn Xuất → Xuất tất cả.",
      "Tải file .xlsx từ mục Lịch sử xuất.",
    ],
  },
  lazada_transactions: {
    title: "Lazada – Báo cáo giao dịch",
    steps: [
      "Trong Seller Center, vào Tài chính → Sao kê tài khoản → Chi tiết giao dịch.",
      "Chọn khoảng thời gian, bấm Xuất CSV.",
    ],
  },
  meta_ads: {
    title: "Meta Ads – Báo cáo theo ngày",
    steps: [
      "Mở Trình quản lý quảng cáo, chọn tài khoản quảng cáo.",
      "Chia nhỏ theo Thời gian → Ngày; cấp Chiến dịch và Nhóm quảng cáo.",
      "Cột: Số tiền đã chi tiêu, Lượt hiển thị, Lượt click vào liên kết, Kết quả, Giá trị chuyển đổi mua hàng.",
      "Bấm Báo cáo → Xuất dữ liệu bảng (.csv).",
    ],
  },
  tiktok_ads: {
    title: "TikTok Ads – Báo cáo theo ngày",
    steps: [
      "Mở TikTok Ads Manager → Báo cáo → Tạo báo cáo tùy chỉnh.",
      "Chiều: Ngày, Chiến dịch, Nhóm quảng cáo. Chỉ số: Chi phí, Lượt hiển thị, Lượt nhấp, Chuyển đổi, Tổng giá trị mua hàng.",
      "Xuất CSV.",
    ],
  },
  google_ads: {
    title: "Google Ads – Báo cáo chiến dịch theo ngày",
    steps: [
      "Mở Google Ads → Báo cáo → Báo cáo được xác định trước → Thời gian → Ngày.",
      "Thêm Chiến dịch, Nhóm quảng cáo và cột Chi phí, Lượt hiển thị, Lượt nhấp, Lượt chuyển đổi, Giá trị chuyển đổi.",
      "Tải xuống dạng .csv.",
    ],
  },
  product_costs: {
    title: "Giá vốn",
    steps: [
      "Tải file mẫu giá vốn của DataxLand ở nút bên dưới.",
      "Mỗi dòng: mã SKU, giá vốn (₫), ngày áp dụng (dd/mm/yyyy).",
    ],
    note: "Không bắt buộc. Không có giá vốn thì kết quả tính lãi trước giá vốn.",
  },
};
