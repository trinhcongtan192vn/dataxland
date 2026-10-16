# DataxLand – Tài liệu yêu cầu sản phẩm (PRD)

| | |
|---|---|
| Phiên bản | 0.3 |
| Ngày | 16/10/2026 |
| Chủ sở hữu | Trịnh Công Tân |
| Trạng thái | Đã duyệt |
| Đầu vào | `docs/architecture.md` v0.3 |
| Đầu ra | `docs/specs/*` cho Claude Code |

---

## 1. Tóm tắt

DataxLand bán năng lực của một trưởng nhóm data cho SME dưới dạng thuê bao tháng. Mỗi khách nhận:

- số liệu đã chuẩn hóa từ mọi kênh bán và quảng cáo;
- báo cáo một trang mỗi tuần, gửi thẳng vào Telegram;
- dashboard và sổ tay chỉ số trên cổng web;
- AI hỏi đáp trên chính dữ liệu của họ, hỏi được ngay trong Telegram.

Phía sau là một nền tảng giúp một người phục vụ được nhiều khách cùng ngách, vì bộ chỉ số và quy trình được dùng lại.

PRD này mô tả **giai đoạn 1 (MVP, khách 1–3)** chi tiết đến mức tiêu chí nghiệm thu. Giai đoạn 2 và 3 chỉ ở mức danh sách tính năng.

Hai gói ra mắt:

- **Seller đa sàn:** dành cho chủ shop bán trên Shopee, TikTok Shop, Lazada.
- **Agency quảng cáo:** dành cho agency chạy Meta, TikTok, Google và Amazon Ads cho các shop.

---

## 2. Vấn đề

| Ai | Vấn đề | Hậu quả |
|---|---|---|
| Chủ shop đa sàn | Doanh thu, phí sàn, phí thanh toán, quảng cáo, vận chuyển, hoàn hàng nằm ở nhiều nơi | Không biết lãi thật theo kênh và theo SKU; có SKU lỗ mà vẫn chạy quảng cáo |
| Agency quảng cáo | Số liệu nằm trên nhiều nền tảng quảng cáo; ROAS nền tảng báo khác doanh thu thật trên sàn | Mất nhiều giờ làm báo cáo cho khách; khó chứng minh hiệu quả |
| Cả hai | Không có người hiểu cả dữ liệu lẫn nghiệp vụ; thuê toàn thời gian thì đắt | Báo cáo làm tay, chậm, mỗi người tính một kiểu |

Bằng chứng từ thị trường: theo khảo sát của TopCV, doanh nghiệp Việt ngại ứng dụng AI và dữ liệu vì chi phí triển khai và duy trì (46,74%), thiếu chuyên gia (43,67%) và khó tích hợp (35,26%).

**Giả định cần kiểm chứng ở giai đoạn 1:**

- **G1:** chủ shop sẵn sàng trả thuê bao tháng cho báo cáo lãi lỗ thật.
- **G2:** agency sẵn sàng trả để giảm giờ làm báo cáo và có số đối chiếu với doanh thu thật.

---

## 3. Mục tiêu và chỉ số thành công

### 3.1 Mục tiêu kinh doanh của giai đoạn 1

Giai đoạn 1 qua **Cổng 1** khi có 3 khách trả tiền, và ít nhất 2 khách mở báo cáo tuần trong ít nhất 3 trên 4 tuần gần nhất.

### 3.2 Chỉ số sản phẩm

Mục tiêu sẽ được hiệu chỉnh sau khách đầu tiên.

| Chỉ số | Định nghĩa | Mục tiêu GĐ1 | Mục tiêu GĐ2 |
|---|---|---|---|
| Tỷ lệ mở báo cáo tuần | Số báo cáo được mở chia số báo cáo đã gửi, theo khách | ≥ 75% | ≥ 75% |
| Thời gian thiết lập | Từ khi đủ quyền truy cập nguồn đến khi gửi được báo cáo đầu tiên | ≤ 10 ngày làm việc | ≤ 3 ngày làm việc |
| Giờ người mỗi khách | Giờ team dùng cho một khách mỗi tháng | Đo làm mốc | ≤ 8 giờ |
| Độ tươi dữ liệu | Tỷ lệ thời gian dữ liệu không cũ quá ngưỡng | ≥ 95% | ≥ 99% |
| Lỗi số liệu khách phát hiện | Số lần khách báo số sai mà hệ thống chưa bắt được | ≤ 1 lần mỗi khách mỗi tháng | 0 |
| Chuyển đổi từ kiểm tra sức khỏe | Số lượt kiểm tra dẫn đến hợp đồng | Đo làm mốc | ≥ 20% |
| Độ chính xác AI hỏi đáp | Tỷ lệ đúng trên bộ câu hỏi đánh giá | (GĐ2) | ≥ 90% |

---

## 4. Người dùng

| Mã | Người dùng | Cần gì | Dùng phần nào |
|---|---|---|---|
| U1 | **Chủ shop** (owner, gói Seller) | Biết lãi thật, SKU nào lỗ, kênh nào đáng đầu tư; mỗi tuần mất ít phút, không phải mở thêm app | Telegram bot (báo cáo, cảnh báo, hỏi AI), dashboard, sổ tay chỉ số, nhập giá vốn |
| U2 | **Nhân viên của shop** (member) | Xem số trong phạm vi được giao | Dashboard, báo cáo, Telegram bot |
| U3 | **Quản lý tài khoản agency** (partner, gói Agency) | Báo cáo cho nhiều shop nhanh; đối chiếu ROAS nền tảng với doanh thu thật; theo dõi tiến độ chi ngân sách | Trang agency, dashboard gói Agency, báo cáo tuần, Telegram bot |
| U4 | **Trưởng nhóm data** (data_lead, nội bộ) | Vận hành nhiều khách trong một màn hình; duyệt báo cáo và cấu hình | Màn hình vận hành, duyệt báo cáo, thiết lập khách mới |
| U5 | **Analytics engineer** (engineer, nội bộ) | Thêm nguồn, sửa model nhanh, biết khi nào hỏng | Kho mã, CI, cảnh báo, agent nội bộ |
| U6 | **Khách tiềm năng** | Biết mình đang mất tiền ở đâu trước khi trả tiền | Kiểm tra sức khỏe dữ liệu |

---

## 5. Phạm vi theo giai đoạn

| Tính năng | GĐ1 | GĐ2 | GĐ3 |
|---|---|---|---|
| Connector Shopee, TikTok Shop, Lazada (dlt) | ✔ | | |
| Quảng cáo Meta, TikTok, Google, Amazon Ads và Amazon Seller Central (Windsor.ai) | ✔ | | |
| Connector hãng vận chuyển (GHN, GHTK, J&T) | | ✔ | |
| Mô hình dữ liệu chung, kiểm tra chất lượng, đối soát | ✔ | | |
| Dịch vụ chỉ số (Cube), gói Seller và gói Agency | ✔ | | |
| Nhập giá vốn trên cổng và qua file | ✔ | | |
| Nhập ngân sách quảng cáo theo tháng và nền tảng | ✔ | | |
| Ngân sách theo chiến dịch | | ✔ | |
| Báo cáo tuần, duyệt tay, gửi qua Telegram và email | ✔ | | |
| Telegram bot: liên kết tài khoản, nhận báo cáo và cảnh báo, lệnh nhanh | ✔ | | |
| Hỏi AI qua Telegram | | ✔ | |
| Dashboard theo gói | ✔ | | |
| Sổ tay chỉ số | ✔ | | |
| Nhật ký quyết định (nhập tay) | ✔ | | |
| Nhật ký quyết định tự đo lại | | | ✔ |
| Kiểm tra sức khỏe dữ liệu từ file | ✔ | | |
| Sổ đăng ký khách, Dagster, màn hình vận hành cơ bản | ✔ | | |
| Màn hình vận hành đầy đủ (chi phí, giờ người) | | ✔ | |
| Biểu mẫu thiết lập khách mới tự sinh cấu hình | | ✔ | |
| Trang agency (nhiều khách) | ✔ (cơ bản) | ✔ (đầy đủ) | |
| Ghép định danh có AI | | ✔ | |
| AI hỏi đáp trên cổng | | ✔ | |
| Agent nội bộ | | ✔ | |
| So sánh ngành | | | ✔ |

---

## 6. Hành trình chính

### J1. Từ kiểm tra sức khỏe đến khách trả tiền (U6 → U1)

1. Khách tiềm năng vào trang kiểm tra sức khỏe, nhập email, tải file xuất từ sàn và tài khoản quảng cáo.
2. Trong vòng 1 ngày làm việc, khách nhận email kèm link báo cáo. Báo cáo nêu bằng tiền:
   - phí đã ăn vào lãi bao nhiêu;
   - các SKU đang lỗ sau phí;
   - hoàn hàng bất thường;
   - số không khớp giữa các nguồn.
3. Team gọi tư vấn và chào gói.
4. Khách ký hợp đồng. Dữ liệu và ánh xạ từ lượt kiểm tra được chuyển sang thiết lập chính thức.

### J2. Thiết lập khách mới (U4, U1)

1. Trưởng nhóm data điền thông tin khách: kênh, nguồn, gói, người nhận.
2. Khách cấp quyền API cho các sàn và tài khoản quảng cáo, nhập giá vốn, và liên kết Telegram.
3. Hệ thống tạo môi trường, nạp dữ liệu lịch sử, chạy kiểm tra và đối soát.
4. Trưởng nhóm data rà số, sửa ánh xạ nếu cần, rồi gửi báo cáo đầu tiên.
5. Buổi bàn giao: đi qua sổ tay chỉ số và báo cáo đầu cùng khách.

### J3. Vòng tuần (U1, U3, U4)

1. Sáng thứ Hai, hệ thống dựng báo cáo tuần cho từng khách. Ở GĐ2 kèm nhận định nháp do AI soạn.
2. Trưởng nhóm data viết hoặc sửa nhận định, rồi bấm gửi.
3. Khách nhận tin Telegram (và email) có 3 số chính và link. Hệ thống ghi nhận khách mở báo cáo.
4. Giữa tuần, khách gõ `/week` trong Telegram để xem nhanh 3 số chính. Ở GĐ2, khách hỏi tự do và AI trả lời ngay trong Telegram.
5. Khi có số bất thường giữa tuần, trưởng nhóm data xác nhận rồi mới chuyển cảnh báo cho khách. Ở GĐ2 bước này được tự động hóa một phần.

### J4. Rà soát tháng (U1, U4)

1. Buổi họp 30 phút xem số tháng.
2. Ghi các quyết định vào nhật ký, mỗi quyết định kèm chỉ số dùng để đo lại và ngày đo lại.
3. Đến ngày đo lại, team ghi kết quả. Ở GĐ3 hệ thống tự lấy số.

### J5. Agency xem nhiều khách (U3)

1. Agency đăng nhập và thấy danh sách các shop đã cấp quyền.
2. Trang tổng hợp hiện chi tiêu, tiến độ chi so với ngân sách, ROAS nền tảng so với ROAS thật, TACOS (với Amazon), sắp xếp theo mức cần chú ý.
3. Agency bấm vào từng shop để xem dashboard gói Agency của shop đó.

---

## 7. Yêu cầu chức năng

Quy ước:

- **Mã:** `FR-<nhóm>-<số>`.
- **Ưu tiên:** P0 là bắt buộc để qua Cổng 1; P1 là cần có trong GĐ1; P2 là GĐ2 trở đi.
- **Hệ thống:** S1–S8, theo `architecture.md`.
- Mỗi FR sẽ có spec riêng trong `docs/specs/`.

### 7.1 Nạp dữ liệu (S1)

| Mã | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| FR-ING-01 | Connector dlt cho Shopee lấy đơn, dòng đơn, trạng thái, phí (hoa hồng, dịch vụ, thanh toán), quyết toán, hoàn hàng | P0 | Với shop thử nghiệm, số đơn và doanh thu 30 ngày khớp báo cáo trong Seller Centre trong phạm vi ngưỡng đối soát |
| FR-ING-02 | Connector dlt cho TikTok Shop, cùng phạm vi như FR-ING-01 | P0 | Như FR-ING-01 |
| FR-ING-03 | Connector dlt cho Lazada, cùng phạm vi như FR-ING-01 | P1 | Như FR-ING-01 |
| FR-ING-04 | Cấu hình Windsor.ai đổ Meta, TikTok, Google, Amazon Ads và Amazon Seller Central vào `t_<id>_raw` theo hợp đồng nạp | P0 | Bảng theo đúng quy ước tên; có `_dx_loaded_at`; chi tiêu theo ngày khớp giao diện nền tảng |
| FR-ING-05 | Nạp lịch sử khi thiết lập | P0 | Lấy được tối thiểu 90 ngày, hoặc tối đa sàn cho phép nếu ít hơn |
| FR-ING-06 | Đồng bộ định kỳ: mặc định 6 giờ (gói Seller), 3 giờ (gói Agency), chỉnh được theo khách | P0 | Lịch trong cấu hình khách được Dagster áp dụng; đổi cấu hình thì lịch đổi theo mà không cần sửa code |
| FR-ING-07 | Nạp tăng dần và cập nhật lại đơn đã thay đổi trạng thái trong 30 ngày gần nhất | P0 | Đơn chuyển sang hoàn hoặc hủy sau khi giao được phản ánh ở lần đồng bộ kế tiếp |
| FR-ING-08 | Token sàn tự làm mới; báo lỗi khi quyền bị thu hồi | P0 | Token hết hạn được làm mới không cần người; quyền bị thu hồi thì phát `sync.failed` kèm lý do |
| FR-ING-09 | Connector hãng vận chuyển (GHN, GHTK, J&T) | P2 | Phí và COD theo vận đơn khớp file đối soát của hãng |

### 7.2 Chuẩn hóa, mô hình chung và chất lượng (S1)

| Mã | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| FR-MOD-01 | Model `stg` cho mỗi nguồn: đổi tên, ép kiểu, múi giờ `Asia/Ho_Chi_Minh`, map trạng thái và lý do hoàn qua seed | P0 | Mọi trạng thái nguồn đều được map; trạng thái lạ làm test lỗi |
| FR-MOD-02 | Mô hình chung gồm 9 bảng theo `architecture.md` mục 5.3 | P0 | Có test khóa, test quan hệ và test not null cho mọi khóa |
| FR-MOD-03 | Quy đổi tiền tệ: giữ số tiền gốc và số quy đổi sang VND theo tỷ giá chuyển khoản bán ra của Vietcombank tại ngày giao dịch; ngày không có tỷ giá dùng ngày làm việc gần nhất trước đó | P0 | Đơn và quảng cáo bằng USD (Amazon) có cả `amount_original`, `currency`, `amount_vnd` |
| FR-MOD-04 | Ghi đè ánh xạ theo khách | P1 | Khách có trạng thái riêng chỉ cần thêm file override, không sửa model |
| FR-MOD-05 | Phân bổ chi phí không gắn được vào đơn, theo quy tắc trong cấu hình (theo doanh thu, theo số đơn, không phân bổ) | P0 | Tổng chi phí trước và sau phân bổ bằng nhau |
| FR-DQ-01 | Test độ tươi theo `freshness_hours` của khách | P0 | Quá ngưỡng thì chặn báo cáo và phát `test.failed` |
| FR-DQ-02 | Test đối soát số đơn và doanh thu theo ngày với báo cáo tổng của nguồn; ngưỡng mặc định 1%, ghi đè được theo nguồn | P0 | Lệch quá ngưỡng thì chặn; thông báo nêu ngày, nguồn và mức lệch |
| FR-DQ-03 | Phát hiện bất thường khối lượng dữ liệu (Elementary) | P1 | Mức cảnh báo, không chặn |
| FR-DQ-04 | Khi có test chặn, không làm mới Cube và không dựng báo cáo cho khách đó | P0 | Kiểm thử bằng một test cố ý lỗi: dashboard giữ số của lần chạy tốt trước và hiện thời điểm cập nhật cũ |

### 7.3 Dịch vụ chỉ số (S2)

| Mã | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| FR-MET-01 | Mỗi chỉ số định nghĩa trong một file YAML theo `architecture.md` mục 6.2 | P0 | `semantic/build.py` từ chối file thiếu trường bắt buộc |
| FR-MET-02 | Sinh model Cube, sổ tay chỉ số và ngữ cảnh AI từ YAML | P0 | Không có model Cube nào viết tay; CI báo lỗi nếu `semantic/cube/` lệch với YAML |
| FR-MET-03 | Gói Seller với các chỉ số ở `architecture.md` mục 6.3 | P0 | Mỗi chỉ số có ít nhất một test giá trị trên dữ liệu mẫu |
| FR-MET-04 | Gói Agency với các chỉ số ở `architecture.md` mục 6.4 | P0 | Như FR-MET-03 |
| FR-MET-05 | Cube đa khách: mọi truy vấn phải có `tenant_id` trong securityContext và chỉ đọc dataset của khách đó | P0 | Truy vấn không có hoặc sai `tenant_id` bị từ chối; có kiểm thử với 2 khách giả lập |
| FR-MET-06 | API `POST /v1/metrics/query` trả số kèm `metric_version` và `data_as_of` | P0 | Mọi phản hồi có hai trường này |
| FR-MET-07 | Phát hiện bất thường theo ngưỡng trong YAML, phát `metric.anomaly` | P1 | Số giả lập lệch 40% so với trung bình 4 tuần thì phát sự kiện |
| FR-MET-08 | Phiên bản chỉ số: đổi công thức thì tăng version và ghi lịch sử | P0 | Sổ tay hiện lịch sử thay đổi; báo cáo cũ giữ version đã dùng |

### 7.4 Dữ liệu khách nhập tay (S6)

| Mã | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| FR-INP-01 | Bảng giá vốn theo SKU trên cổng: thêm, sửa, có ngày hiệu lực | P0 | Sửa giá vốn từ một ngày chỉ ảnh hưởng đơn từ ngày đó |
| FR-INP-02 | Tải giá vốn hàng loạt bằng file Excel theo mẫu | P0 | File mẫu tải được từ cổng; dòng lỗi được báo rõ dòng và lý do, các dòng hợp lệ vẫn được nhận |
| FR-INP-03 | Cảnh báo SKU chưa có giá vốn | P0 | Dashboard và báo cáo hiện số SKU và doanh thu chưa có giá vốn; chỉ số lãi ghi chú là chưa đầy đủ |
| FR-INP-04 | Ngân sách quảng cáo theo tháng và nền tảng (gói Agency) | P0 | Nhập trên cổng; `budget_pacing` dùng số này |
| FR-INP-05 | Ngân sách theo chiến dịch | P2 | |

### 7.5 Báo cáo tuần (S6, S4)

| Mã | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| FR-REP-01 | Dựng báo cáo tuần theo lịch trong cấu hình khách (mặc định thứ Hai 07:00) | P0 | Bản nháp xuất hiện ở `/ops/reports` sau khi lần chạy tốt gần nhất hoàn tất |
| FR-REP-02 | Nội dung gói Seller: doanh thu thực nhận, lãi sau phí, biên đóng góp, so với tuần trước; top 5 SKU lãi và lỗ; tỷ lệ hoàn; cảnh báo dữ liệu. Đơn chưa quyết toán trong cửa sổ tạm tính của sàn (mặc định 14 ngày, cấu hình được theo sàn) được tính là số tạm tính và báo tỷ lệ | P0 | Mọi số lấy qua API chỉ số |
| FR-REP-03 | Nội dung gói Agency: chi tiêu theo nền tảng, tiến độ ngân sách, ROAS nền tảng so với ROAS thật, TACOS và ACOS (Amazon), chiến dịch cần chú ý (cờ theo FR-AGY-01, và chiến dịch trong top 10 chi tiêu có ROAS nền tảng giảm quá ngưỡng so với 4 tuần trước) | P0 | Mọi số lấy qua API chỉ số |
| FR-REP-04 | Ô nhận định: trưởng nhóm data viết hoặc sửa trước khi gửi (GĐ1 viết tay; GĐ2 có bản nháp từ AI) | P0 | Báo cáo không gửi được khi ô nhận định trống |
| FR-REP-05 | Gửi: tin nhắn có 3 số chính và link vào cổng, qua Telegram và email theo kênh khách đã bật. Ba số chính: gói Seller là doanh thu thực nhận, lãi sau phí, % thay đổi lãi so với kỳ trước; gói Agency là tổng chi quảng cáo, ROAS thật, tiến độ ngân sách | P0 | Cùng một mẫu nội dung cho hai kênh; gửi trong vòng 10 phút sau khi duyệt |
| FR-REP-06 | Ghi nhận việc mở báo cáo theo người nhận (mở link, hoặc bấm nút xem trong Telegram) | P0 | Màn hình vận hành hiện trạng thái đã mở hay chưa |
| FR-REP-07 | Lưu trữ báo cáo cũ, xem lại được | P0 | Báo cáo cũ hiện đúng số tại thời điểm gửi, không tính lại |

### 7.6 Dashboard và sổ tay chỉ số (S6)

| Mã | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| FR-DSH-01 | Dashboard gói Seller: tổng quan lãi lỗ, lãi theo kênh, lãi theo SKU, phí theo loại, hoàn hàng | P0 | Lọc theo khoảng ngày và kênh; tải dưới 3 giây khi có pre-aggregation |
| FR-DSH-02 | Dashboard gói Agency: chi tiêu và hiệu quả theo nền tảng, chiến dịch, ROAS nền tảng so với thật, tiến độ ngân sách | P0 | Như FR-DSH-01 |
| FR-DSH-03 | Mỗi biểu đồ hiện thời điểm dữ liệu cập nhật; bấm vào tên chỉ số thì mở sổ tay | P0 | |
| FR-DSH-04 | Sổ tay chỉ số: tên tiếng Việt, mô tả, công thức diễn giải, nguồn, phiên bản, lịch sử | P0 | Sinh tự động; không có trang nào viết tay |
| FR-DSH-05 | Xuất bảng ra CSV | P1 | |

### 7.7 Nhật ký quyết định (S6)

| Mã | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| FR-DEC-01 | Tạo quyết định: ngày, nội dung, người quyết, chỉ số đo (chọn từ thư viện), giá trị lúc quyết định (tự lấy), mục tiêu, ngày đo lại | P1 | Giá trị lúc quyết định lấy qua API chỉ số |
| FR-DEC-02 | Nhắc team khi đến ngày đo lại; team ghi giá trị sau và kết luận | P1 | Thông báo cho team (Telegram nội bộ và email) vào ngày đo lại |
| FR-DEC-03 | Tự lấy giá trị sau khi đến ngày đo lại | P2 (GĐ3) | |
| FR-DEC-04 | Báo cáo giá trị cuối kỳ hợp đồng | P2 | |

### 7.8 Kiểm tra sức khỏe dữ liệu (S5)

| Mã | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| FR-HC-01 | Trang công khai: nhập email, chọn loại file, tải file xuất (Shopee, TikTok Shop, Lazada, Meta, TikTok Ads, Google Ads) | P0 | Nhận Excel và CSV; báo lỗi rõ khi file sai mẫu |
| FR-HC-02 | Xử lý file bằng chính adapter và chỉ số của gói Seller trong dataset tạm | P0 | Không có code tính chỉ số riêng cho phần kiểm tra sức khỏe |
| FR-HC-03 | Báo cáo kết quả nêu bằng tiền: phí theo loại, SKU lỗ sau phí, hoàn hàng, chênh lệch giữa nguồn | P0 | Trưởng nhóm data duyệt trước khi gửi link |
| FR-HC-04 | Xóa dữ liệu tạm sau 14 ngày nếu chưa chuyển sang thiết lập; ghi rõ thời hạn trên trang tải | P0 | Job xóa chạy hằng ngày, có log |
| FR-HC-05 | Chuyển lượt kiểm tra thành khách: ánh xạ đã làm trở thành bản nháp cấu hình khách | P1 | |

### 7.9 Vận hành (S4)

| Mã | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| FR-OPS-01 | Sổ đăng ký: `tenants/<id>.yml` trong git, đồng bộ vào Postgres khi merge | P0 | Sửa file và merge thì API trả cấu hình mới trong vòng 5 phút |
| FR-OPS-02 | Script tạo khách: dataset, tài khoản dịch vụ, quyền, secret, partition Dagster | P0 | Chạy lại không tạo trùng (idempotent) |
| FR-OPS-03 | Pipeline Dagster theo khách: sync → dbt build → test → làm mới Cube → bất thường → báo cáo | P0 | Bước lỗi thì dừng các bước sau và phát sự kiện |
| FR-OPS-04 | Màn hình vận hành: mỗi khách một dòng, gồm lần đồng bộ gần nhất, test lỗi, trạng thái báo cáo | P0 | Dữ liệu trên màn hình trễ không quá 5 phút |
| FR-OPS-05 | Thông báo cho team qua nhóm Telegram nội bộ và email cho mọi lỗi chặn | P0 | Thông báo trong vòng 10 phút kể từ khi lỗi |
| FR-OPS-06 | Màn hình vận hành thêm chi phí theo khách (BigQuery, Windsor, Claude) và giờ người | P2 | |
| FR-OPS-07 | Biểu mẫu thiết lập sinh bản nháp cấu hình, mở PR | P2 | |
| FR-OPS-08 | Lớp thông báo độc lập với kênh: mỗi kênh là một adapter cùng giao diện; thêm kênh mới không sửa logic gửi | P0 | Thêm một adapter giả lập trong kiểm thử mà không đổi code của trung tâm thông báo |
| FR-OPS-09 | Script xóa dữ liệu của một người mua trên mọi lớp | P1 | Chạy trên dữ liệu mẫu: không còn bản ghi gốc hay băm của người đó |

### 7.10 Tài khoản và phân quyền (S6)

| Mã | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| FR-AUTH-01 | Đăng nhập bằng Firebase Auth (email và Google) | P0 | |
| FR-AUTH-02 | Vai trò `owner`, `member`, `partner`, `data_lead`, `engineer` bằng custom claims | P0 | Kiểm thử ma trận quyền theo `architecture.md` mục 9.2 |
| FR-AUTH-03 | Owner mời và gỡ member; giới hạn chỉ số member được xem | P1 | |
| FR-AUTH-04 | Owner cấp và thu quyền cho agency | P0 | Thu quyền thì agency mất quyền xem ngay ở lần gọi API kế tiếp |
| FR-AUTH-05 | Mặc định ẩn thông tin cá nhân người mua với mọi vai trò | P0 | API không trả số điện thoại hay email người mua |

### 7.11 Trang agency (S6)

| Mã | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| FR-AGY-01 | Danh sách shop đã cấp quyền, kèm chi tiêu tháng, tiến độ ngân sách, ROAS thật, cờ cần chú ý. Ba cờ mặc định, ngưỡng chỉnh được theo khách: chi vượt tiến độ ngân sách trên 15%; ROAS thật 7 ngày giảm trên 25% so với trung bình 4 tuần trước; ROAS nền tảng cao hơn ROAS thật trên 50% | P0 | Chỉ hiện shop đã cấp quyền |
| FR-AGY-02 | Bấm vào một shop để xem dashboard gói Agency của shop đó | P0 | |
| FR-AGY-03 | Báo cáo tuần gộp cho agency (nhiều shop) | P2 | |

### 7.12 Telegram bot (S6b)

| Mã | Yêu cầu | Ưu tiên | Tiêu chí nghiệm thu |
|---|---|---|---|
| FR-TG-01 | Liên kết tài khoản: người dùng tạo mã trên cổng (dùng một lần, hết hạn 10 phút), gửi `/start <mã>` cho bot | P0 | Mã đã dùng hoặc hết hạn bị từ chối; chat chưa liên kết chỉ nhận hướng dẫn, không nhận số liệu |
| FR-TG-02 | Nhận báo cáo tuần và cảnh báo trong Telegram, cùng nội dung với email, kèm nút mở báo cáo trên cổng | P0 | Khách liên kết nhận được tin trong vòng 10 phút sau khi duyệt |
| FR-TG-03 | Lệnh nhanh: `/report` (báo cáo mới nhất), `/week` và `/month` (3 số chính như FR-REP-05), `/help` | P0 | Số trong lệnh khớp với cổng tại cùng thời điểm; mọi số lấy qua API chỉ số |
| FR-TG-04 | Gỡ liên kết: `/unlink` trong chat, hoặc owner gỡ trên cổng | P0 | Sau khi gỡ, tin nhắn kế tiếp của chat đó chỉ nhận hướng dẫn liên kết |
| FR-TG-05 | Liên kết nhóm Telegram: chỉ owner liên kết được nhóm và chọn phạm vi chỉ số cho nhóm; bot trả lời trong nhóm theo phạm vi đó | P1 | Thành viên nhóm không có tài khoản vẫn đọc được tin trong nhóm, nhưng chỉ trong phạm vi owner đã chọn |
| FR-TG-06 | Hỏi AI bằng tin nhắn tự do trong Telegram, cùng engine và ràng buộc với FR-AI-01 | P2 | Cùng câu hỏi cho ra cùng câu trả lời trên cổng và trên Telegram |
| FR-TG-07 | Giới hạn tần suất theo chat cho lệnh và câu hỏi AI | P1 | Vượt giới hạn thì bot trả lời là cần chờ, không gọi AI |
| FR-TG-08 | Không gửi thông tin cá nhân của người mua qua Telegram | P0 | Kiểm thử: câu hỏi về một người mua cụ thể bị từ chối |

### 7.13 Giai đoạn 2 trở đi (mức danh sách)

| Mã | Yêu cầu | GĐ |
|---|---|---|
| FR-ID-01 | Ghép SKU xuyên kênh theo quy tắc và gợi ý của AI, có hàng chờ duyệt | 2 |
| FR-ID-02 | Gộp hồ sơ người mua khi có định danh | 2 |
| FR-AI-01 | AI hỏi đáp qua MCP, chỉ 3 công cụ đọc chỉ số; mỗi câu trả lời nêu chỉ số, phiên bản, khoảng thời gian, thời điểm dữ liệu; dùng chung cho cổng và Telegram | 2 |
| FR-AI-02 | Câu hỏi chưa có chỉ số được ghi vào hàng chờ đề xuất | 2 |
| FR-AI-03 | Bộ đánh giá AI cho mỗi gói chạy trong CI | 2 |
| FR-AGT-01 | Agent nội bộ: `new-adapter`, `review-change`, `weekly-insight`, `incident-triage`, `onboarding-draft` | 2 |
| FR-BMK-01 | So sánh ngành: chỉ khách đồng ý, chỉ số tổng hợp, tối thiểu 5 doanh nghiệp mỗi nhóm | 3 |

---

## 8. Yêu cầu phi chức năng

| Mã | Nhóm | Yêu cầu |
|---|---|---|
| NFR-01 | Tách biệt dữ liệu | Không truy vấn nào đọc chéo hai khách; có kiểm thử tự động với 2 khách giả lập trong CI |
| NFR-02 | Bảo mật | Bí mật chỉ nằm trong Secret Manager; mọi endpoint lấy `tenant_id` từ token; HTTPS cho mọi kết nối |
| NFR-03 | Thông tin cá nhân | Số điện thoại và email người mua chỉ ở dạng gốc trong `raw` và `stg`; các lớp trên chỉ có dạng băm |
| NFR-04 | Hiệu năng | Dashboard tải dưới 3 giây (p95) với pre-aggregation; API chỉ số dưới 2 giây (p95) |
| NFR-05 | Độ tươi | Dữ liệu không cũ quá `freshness_hours` trong ≥ 95% thời gian (GĐ1) |
| NFR-06 | Khả dụng | GĐ1: chấp nhận gián đoạn tối đa 1 ngày làm việc; sao lưu Postgres hằng ngày, thử khôi phục mỗi tháng |
| NFR-07 | Khả năng chuyển nền tảng | SQL trong `core` và `marts` không dùng hàm riêng của BigQuery; CI chạy được toàn bộ model trên DuckDB |
| NFR-08 | Chi phí | Chi phí hạ tầng và công cụ theo dõi được theo từng khách (nhãn `tenant_id`) |
| NFR-09 | Ngôn ngữ | Giao diện, sổ tay, báo cáo bằng tiếng Việt; số tiền định dạng `1.234.567 ₫` |
| NFR-10 | Truy vết | Mọi số trong báo cáo truy được về chỉ số, phiên bản và lần chạy |
| NFR-11 | Tuân thủ | Đáp ứng Luật 91/2025/QH15 và Nghị định 356/2025/NĐ-CP; có hợp đồng xử lý dữ liệu mẫu trước khách đầu tiên; hợp đồng nêu rõ tin nhắn qua Telegram được lưu trên máy chủ của Telegram |
| NFR-12 | Kênh liên lạc | Email luôn bật song song với Telegram; mọi tính năng của bot đều có trên cổng web; Telegram không hoạt động thì khách vẫn nhận được báo cáo |

---

## 9. Đóng gói và giá

Chi tiết giá nằm ngoài PRD này (xem tài liệu phương án kinh doanh). Các ràng buộc sản phẩm được giữ như sau:

- Kiểm tra sức khỏe dữ liệu: miễn phí hoặc giá cố định thấp.
- Thiết lập: phí một lần.
- Thuê bao tháng theo gói, có bậc theo số nguồn dữ liệu (không theo dung lượng).
- Agency: giá theo số shop được quản lý (cần chốt ở vòng chào bán thử).

Sản phẩm phải đo được số nguồn của từng khách và số shop của từng agency để phục vụ việc tính giá.

---

## 10. Phụ thuộc, giả định và rủi ro

| Loại | Nội dung | Ảnh hưởng | Xử lý |
|---|---|---|---|
| Phụ thuộc | Ứng dụng đối tác Shopee, TikTok Shop, Lazada được duyệt | Chặn FR-ING-01..03 | Đăng ký ngay; dùng tạm connector sàn của Windsor.ai nếu dữ liệu phí đủ sâu |
| Phụ thuộc | Tài khoản Windsor.ai | Chặn FR-ING-04 | Mở tài khoản dùng thử khi bắt đầu xây |
| Phụ thuộc | Ý kiến luật sư về điều kiện kinh doanh dịch vụ xử lý dữ liệu và chuyển dữ liệu ra nước ngoài | Chặn ký khách đầu tiên | Hỏi luật sư song song với việc xây |
| Giả định | Shop thử nghiệm sẵn sàng cấp quyền API và nhập giá vốn | Chặn kiểm thử | Chọn 1–2 shop quen làm đối tác thử nghiệm |
| Rủi ro | Sàn che thông tin người mua | Không tính được khách quay lại cho gói Seller | Chỉ số `repeat_customer_rate` chỉ bật khi có định danh |
| Rủi ro | Phí trên sàn được quyết toán trễ vài ngày | Lãi tuần gần nhất chưa chính xác | Ghi chú "số tạm tính" cho các ngày chưa quyết toán; báo cáo tuần tính lại tuần trước |
| Rủi ro | Chi phí Windsor tăng theo số tài khoản | Biên lợi nhuận | Theo dõi chi phí mỗi khách; đường lui sang dlt hoặc Airbyte |
| Rủi ro | Telegram bị hạn chế truy cập tại Việt Nam (cơ quan quản lý đã yêu cầu nhà mạng chặn từ tháng 5/2025; tình trạng có thể thay đổi) | Khách không nhận được tin, bot không dùng được | NFR-12; FR-OPS-08 cho phép thêm Zalo mà không sửa logic gửi; hỏi khách về kênh họ dùng được ngay buổi thiết lập |

---

## 11. Ngoài phạm vi

- Ghi ngược dữ liệu vào sàn hay vào tài khoản quảng cáo, ví dụ đổi giá hay tắt chiến dịch.
- Dữ liệu thời gian thực.
- Ứng dụng di động riêng. Cổng web phải dùng tốt trên điện thoại.
- POS, kế toán, CRM và các phần mềm vận hành khác.
- Tối ưu quảng cáo tự động.

---

## 12. Kế hoạch phát hành giai đoạn 1

| Mốc | Nội dung | Tiêu chí hoàn thành |
|---|---|---|
| M0 | Nền móng: repo, CI, VM, Postgres, Firebase Auth, Dagster, Cube chạy với dữ liệu mẫu | Pipeline chạy hết từ đầu đến cuối trên dữ liệu mẫu của 2 khách giả lập |
| M1 | Dữ liệu thật của shop thử nghiệm: Shopee, TikTok Shop, Windsor; mô hình chung; đối soát | Test đối soát qua với shop thử nghiệm |
| M2 | Chỉ số 2 gói, dashboard, sổ tay, nhập giá vốn và ngân sách | Shop thử nghiệm xác nhận số lãi lỗ khớp hiểu biết của họ |
| M3 | Báo cáo tuần, Telegram bot (liên kết, nhận báo cáo, lệnh nhanh), màn hình vận hành, kiểm tra sức khỏe, trang agency cơ bản | Gửi được 2 báo cáo tuần liên tiếp đúng lịch qua Telegram và email |
| M4 | Khách trả tiền 1–3; Lazada; xóa dữ liệu người mua; hợp đồng xử lý dữ liệu | Qua Cổng 1 |

Thời lượng của từng mốc sẽ được ước tính khi viết specs.

---

## Phụ lục. Truy vết yêu cầu sang specs

| Nhóm FR | Hệ thống | File spec |
|---|---|---|
| FR-ING | S1 | `docs/specs/01-ingestion.md` |
| FR-MOD, FR-DQ | S1 | `docs/specs/02-transform-and-quality.md` |
| FR-MET | S2 | `docs/specs/03-semantic-layer.md` |
| FR-OPS | S4 | `docs/specs/04-ops-and-orchestration.md` |
| FR-AUTH, FR-INP | S6 | `docs/specs/05-api-and-auth.md` |
| FR-REP, FR-DSH, FR-DEC, FR-AGY | S6 | `docs/specs/06-portal.md` |
| FR-HC | S5 | `docs/specs/07-health-check.md` |
| FR-TG | S6b | `docs/specs/08-telegram-bot.md` |
| FR-AI, FR-AGT (GĐ2) | S7 | `docs/specs/09-ai-layer.md` |
| FR-ID (GĐ2) | S3 | `docs/specs/10-identity-resolution.md` |
| FR-BMK (GĐ3) | S8 | Viết khi bắt đầu giai đoạn 3 |
| NFR | Tất cả | `docs/specs/00-foundation.md` (repo, CI, môi trường, quy ước, `CLAUDE.md`) |
