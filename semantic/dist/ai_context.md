# Thư viện chỉ số DataxLand (tự sinh – không sửa tay)

| metric | Tên | Gói | Đơn vị | Phiên bản | Từ đồng nghĩa | Công thức |
|---|---|---|---|---|---|---|
| `acos` | ACOS (Amazon) | agency | percent | 1.0.0 | acos | Chi quảng cáo Amazon ÷ Doanh thu từ quảng cáo Amazon |
| `ad_spend` | Chi phí quảng cáo | seller, agency | VND | 1.0.0 | chi quảng cáo, tiền quảng cáo, ads, chi tiêu quảng cáo, spend | Tổng spend trên quảng cáo theo ngày |
| `allocated_ad_spend` | Chi quảng cáo phân bổ | seller | VND | 1.0.1 |  | Tổng allocated ad spend trên đơn hàng (gói seller) |
| `aov` | Giá trị đơn trung bình | seller | VND | 1.0.0 | aov, giá trị đơn trung bình | Doanh thu thực nhận ÷ Số đơn |
| `budget` | Ngân sách quảng cáo | agency | VND | 1.0.1 | ngân sách | Tổng budget trên ngân sách quảng cáo theo tháng |
| `budget_pacing` | Tiến độ ngân sách | agency | ratio | 1.0.0 | tiến độ ngân sách, pacing, chi có vượt không | Đã chi trong tháng ÷ Mức chi đúng tiến độ |
| `budget_used_pct` | Tỷ lệ ngân sách đã dùng | agency | percent | 1.0.0 | đã dùng bao nhiêu ngân sách | Đã chi trong tháng ÷ Ngân sách quảng cáo |
| `cancel_rate` | Tỷ lệ hủy | seller | percent | 1.0.0 | tỷ lệ hủy, đơn hủy | Số đơn hủy ÷ Số đơn đặt |
| `clicks` | Lượt nhấp | agency | count | 1.0.0 | click, nhấp | Tổng clicks trên quảng cáo theo ngày |
| `cogs` | Giá vốn hàng bán | seller | VND | 1.0.1 | giá vốn, cogs, tiền hàng | Tổng cogs trên đơn hàng (gói seller) |
| `contribution_margin` | Biên đóng góp | seller | VND | 1.0.0 | biên đóng góp, lãi gộp sau phí | Doanh thu thực nhận - Giá vốn hàng bán - Phí sàn - Phí thanh toán - Phí vận chuyển - Chi phí hoàn hàng |
| `conversions` | Chuyển đổi | agency | count | 1.0.0 | chuyển đổi, conversion, kết quả | Tổng conversions trên quảng cáo theo ngày |
| `cpa` | Chi phí mỗi chuyển đổi (CPA) | agency | VND | 1.0.0 | cpa, giá mỗi chuyển đổi | Chi phí quảng cáo ÷ Chuyển đổi |
| `cpc` | Chi phí mỗi lượt nhấp (CPC) | agency | VND | 1.0.0 | cpc, giá mỗi click | Chi phí quảng cáo ÷ Lượt nhấp |
| `cpm` | Chi phí mỗi nghìn lượt hiển thị (CPM) | agency | VND | 1.0.0 | cpm | Chi phí quảng cáo ÷ Lượt hiển thị × 1000 |
| `ctr` | Tỷ lệ nhấp (CTR) | agency | percent | 1.0.0 | ctr, tỷ lệ nhấp | Lượt nhấp ÷ Lượt hiển thị |
| `gmv` | Tổng giá trị đơn (GMV) | seller | VND | 1.0.0 | gmv, doanh số, tổng giá trị đơn | Tổng gross amount trên đơn hàng (gói seller) (row_type = order) |
| `impressions` | Lượt hiển thị | agency | count | 1.0.0 | hiển thị, impression | Tổng impressions trên quảng cáo theo ngày |
| `mer` | MER (doanh thu trên chi quảng cáo) | agency | ratio | 1.0.0 | mer, marketing efficiency ratio | Tổng giá trị bán (theo ngày bán) ÷ Chi phí quảng cáo |
| `net_margin_pct` | Biên lãi | seller | percent | 1.0.0 | biên lãi, tỷ suất lợi nhuận, margin | Lãi sau phí ÷ Doanh thu thực nhận |
| `net_profit_after_fees` | Lãi sau phí | seller | VND | 1.0.0 | lãi, lời, lợi nhuận, lãi ròng, lãi thật | Biên đóng góp - Chi quảng cáo phân bổ - Chi phí khác |
| `net_revenue` | Doanh thu thực nhận | seller | VND | 1.0.0 | doanh thu, doanh thu thật, tiền về, doanh thu thực | Tổng net revenue trên đơn hàng (gói seller) |
| `order_count` | Số đơn | seller | count | 1.0.0 | số đơn, đơn hàng, lượng đơn | Số order id trên đơn hàng (gói seller) (row_type = order, is_cancelled = False) |
| `other_costs` | Chi phí khác | seller | VND | 1.0.0 | chi phí khác, affiliate | Tổng other cost trên đơn hàng (gói seller) |
| `payment_fees` | Phí thanh toán | seller | VND | 1.0.0 | phí thanh toán, phí giao dịch | Tổng payment fee trên đơn hàng (gói seller) |
| `platform_fees` | Phí sàn | seller | VND | 1.0.0 | phí sàn, hoa hồng, phí cố định | Tổng platform fee trên đơn hàng (gói seller) |
| `platform_vs_actual_gap` | Chênh lệch nền tảng báo và thực tế | agency | percent | 1.0.0 | chênh lệch roas, nền tảng báo cao | (Giá trị chuyển đổi (nền tảng báo) - Doanh thu thực nhận (theo ngày bán)) ÷ Doanh thu thực nhận (theo ngày bán) |
| `repeat_customer_rate` | Tỷ lệ khách quay lại | seller | percent | 1.0.0 | khách quay lại, khách mua lại, tỷ lệ mua lại | Số người mua quay lại ÷ Số người mua có đơn |
| `return_cost` | Chi phí hoàn hàng | seller | VND | 1.0.0 | chi phí hoàn, phí trả hàng | Tổng return cost trên đơn hàng (gói seller) |
| `return_rate` | Tỷ lệ hoàn | seller | percent | 1.0.0 | tỷ lệ hoàn, hoàn hàng, trả hàng | Số đơn hoàn ÷ Số đơn |
| `roas_blended` | ROAS thật | seller, agency | ratio | 1.0.0 | roas thật, roas tổng, hiệu quả quảng cáo thật, blended roas | Doanh thu thực nhận (theo ngày bán) ÷ Chi phí quảng cáo |
| `roas_platform` | ROAS nền tảng | agency | ratio | 1.0.0 | roas nền tảng, roas facebook, roas ads, roas | Giá trị chuyển đổi (nền tảng báo) ÷ Chi phí quảng cáo |
| `shipping_cost` | Phí vận chuyển | seller | VND | 1.0.0 | phí ship, vận chuyển | Tổng shipping cost trên đơn hàng (gói seller) |
| `sku_profit` | Lãi theo SKU | seller | VND | 1.0.0 | lãi sku, sản phẩm lỗ, lãi từng sản phẩm, sku lỗ | Thành phần lãi theo SKU (net_revenue_vnd) - Thành phần lãi theo SKU (cogs_vnd) - Thành phần lãi theo SKU (platform_fee_vnd) - Thành phần lãi theo SKU (payment_fee_vnd) - Thành phần lãi theo SKU (shipping_cost_vnd) - Thành phần lãi theo SKU (return_cost_vnd) - Thành phần lãi theo SKU (allocated_ad_spend_vnd) - Thành phần lãi theo SKU (other_cost_vnd) |
| `spend_mtd` | Đã chi trong tháng | agency | VND | 1.0.1 |  | Tổng spend mtd trên ngân sách quảng cáo theo tháng |
| `tacos` | TACOS (Amazon) | agency | percent | 1.0.0 | tacos, tổng chi quảng cáo trên doanh thu amazon | Chi quảng cáo Amazon ÷ Tổng doanh thu Amazon |

## Chiều

- `adgroup`: Nhóm quảng cáo
- `campaign`: Chiến dịch
- `campaign_name`: Tên chiến dịch
- `channel`: Kênh
- `date`: Ngày
- `is_provisional`: Tạm tính
- `order_status`: Trạng thái đơn
- `platform`: Nền tảng
- `product`: Sản phẩm
- `product_name`: Tên sản phẩm
- `sku`: SKU
