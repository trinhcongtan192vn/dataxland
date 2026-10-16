# Spec 06 – Cổng khách hàng, báo cáo tuần và màn hình vận hành

Hệ thống: S6. Yêu cầu: FR-REP-01..07, FR-DSH-01..05, FR-DEC-01..04, FR-AGY-01..03, FR-INP-01..04 (giao diện), FR-OPS-04 (giao diện), NFR-04, NFR-09, NFR-12.

Phạm vi: ứng dụng `apps/web`, luồng báo cáo tuần (dựng, duyệt, gửi, ghi nhận mở), nhật ký quyết định, trang agency, màn hình vận hành. Endpoint chung ở spec 05; chỉ số ở spec 03.

---

## 1. Cấu trúc ứng dụng

```
apps/web/
  app/
    (public)/
      login/  invite/[token]/  health-check/  health-check/[id]/
    app/
      layout.tsx            # khung khách: chọn khách, menu theo vai trò
      dashboards/seller/  dashboards/agency/
      reports/  reports/[id]/
      metrics/  metrics/[metric]/
      inputs/costs/  inputs/budgets/
      decisions/  decisions/[id]/
      settings/members/  settings/partners/  settings/telegram/
      ask/                  # GĐ2
    partner/  partner/[tenant]/
    ops/
      page.tsx  tenants/[id]/  reports/  reports/[id]/  health-checks/  health-checks/[id]/
    r/[token]/route.ts      # ghi nhận mở báo cáo rồi chuyển hướng
  components/
    charts/  tables/  metric-label.tsx  data-status.tsx  money.tsx
  lib/
    api/                    # client sinh từ OpenAPI (spec 05 mục 10)
    auth/                   # Firebase Auth
    format.ts               # định dạng số, tiền, ngày theo tiếng Việt
    tenant.ts               # khách đang chọn, gửi X-Tenant-Id
```

| Thư viện | Dùng cho |
|---|---|
| TanStack Query | Gọi API phía client, cache theo khóa truy vấn |
| Recharts | Biểu đồ |
| TanStack Table | Bảng có sắp xếp, lọc |
| react-hook-form + zod | Biểu mẫu |
| Firebase JS SDK | Đăng nhập; gắn ID token vào mọi request |

Mọi dữ liệu lấy qua `services/api`. Web không gọi Cube, BigQuery hay Postgres trực tiếp.

## 2. Khung chung

- **Chọn khách:** người dùng thuộc nhiều khách có bộ chọn ở thanh trên. Khách đang chọn lưu trong URL query `?t=<tenant_id>` và gửi qua `X-Tenant-Id`.
- **Menu theo vai trò:** lấy từ `GET /v1/me`. Ẩn mục không có quyền; backend vẫn là nơi chặn.
- **Trạng thái dữ liệu** (`components/data-status.tsx`): mọi trang có số hiện "Cập nhật lúc HH:mm dd/mm" từ `data_as_of`, và các cảnh báo `MISSING_COGS`, `PROVISIONAL`, `STALE` (spec 03 mục 4.3) thành dải thông báo, có link tới trang xử lý (ví dụ `/app/inputs/costs` cho thiếu giá vốn).
- **Tên chỉ số** (`components/metric-label.tsx`): luôn hiện `name_vi`; bấm vào mở ngăn bên với định nghĩa từ sổ tay và link tới `/app/metrics/<metric>` (FR-DSH-03).
- **Định dạng (NFR-09):** tiền `1.234.567 ₫`; số lớn trên biểu đồ rút gọn `1,2 tr ₫`, `3,4 tỷ ₫`; tỷ lệ `12,5%`; ROAS `3,2x`; ngày `dd/mm/yyyy`; tuần "Tuần 41 (06/10–12/10)".

## 3. Dashboard (FR-DSH-01..05)

Bộ lọc chung: khoảng ngày (preset của spec 03 mục 4.1 và chọn tay), kênh hoặc nền tảng (nhiều lựa chọn). Bộ lọc lưu trong URL để chia sẻ được.

### 3.1 Gói Seller `/app/dashboards/seller`

| Khối | Chỉ số | Hiển thị |
|---|---|---|
| Tổng quan | Ba số chính, `gmv`, `contribution_margin`, `net_margin_pct`, `order_count`, `aov` | Thẻ số, so với kỳ trước |
| Lãi lỗ theo thời gian | `net_revenue`, `net_profit_after_fees` theo ngày hoặc tuần | Đường |
| Lãi theo kênh | `net_revenue`, `contribution_margin`, `net_profit_after_fees` theo `platform` | Cột nhóm |
| Phí theo loại | `platform_fees`, `payment_fees`, `shipping_cost`, `allocated_ad_spend`, `return_cost`, `cogs` | Cột chồng theo kênh, kèm tỷ lệ trên doanh thu |
| Lãi theo SKU | `sku_profit`, `net_revenue`, `order_count` theo `product` | Bảng, mặc định sắp lãi tăng dần để SKU lỗ lên đầu; đánh dấu SKU thiếu giá vốn |
| Hoàn hàng | `return_rate`, `cancel_rate` theo thời gian; `return_cost` theo kênh | Đường và cột |

### 3.2 Gói Agency `/app/dashboards/agency`

| Khối | Chỉ số | Hiển thị |
|---|---|---|
| Tổng quan | Ba số chính, `mer`, `roas_platform`, cờ cần chú ý | Thẻ số, danh sách cờ |
| Chi tiêu theo nền tảng | `ad_spend` theo `platform` theo ngày | Cột chồng |
| Tiến độ ngân sách | `budget`, `spend_mtd`, `budget_used_pct`, `budget_pacing` theo nền tảng | Thanh tiến độ có vạch "đúng tiến độ" |
| ROAS nền tảng và thật | `roas_platform` theo nền tảng, `roas_blended`, `platform_vs_actual_gap` | Cột nhóm và đường |
| Phân phối | `impressions`, `clicks`, `ctr`, `cpc`, `cpm`, `conversions`, `cpa` theo nền tảng | Bảng |
| Chiến dịch | Các chỉ số trên theo `campaign` | Bảng, lọc theo nền tảng |
| Amazon | `acos`, `tacos` | Chỉ hiện khi khách có nguồn Amazon |

### 3.3 Yêu cầu chung

- Mỗi khối gọi `POST /v1/metrics/query` một lần; không tính toán số trên web ngoài định dạng.
- Mỗi khối có nút xuất CSV (FR-DSH-05): tạo CSV phía client từ đúng dữ liệu đang hiển thị, tiêu đề cột là `name_vi`, tiền là số nguyên không định dạng, tên file `<metric-block>_<from>_<to>.csv`, mã hóa UTF-8 có BOM để Excel đọc đúng tiếng Việt.
- Hiệu năng (NFR-04): trang tải xong dưới 3 giây (p95) khi Cube có pre-aggregation. Các khối tải song song; khối nào lỗi thì chỉ khối đó hiện lỗi.

## 4. Báo cáo tuần (FR-REP-01..07)

### 4.1 Dữ liệu

| Bảng | Cột chính |
|---|---|
| `reports` | `id`, `tenant_id`, `pack`, `period_start`, `period_end` (tuần ISO trước), `status` (`draft`, `approved`, `sent`, `partially_sent`, `failed`, `superseded`), `snapshot` jsonb, `insight_md`, `actions` jsonb (danh sách việc cần làm), `data_stale`, `run_id`, `built_at`, `approved_by`, `approved_at`, `sent_at`, `template_version`; GĐ2 thêm `insight_draft_md`, `actions_draft` (spec 09 mục 8) |
| `report_recipients` | `id`, `report_id`, `channel` (`telegram`, `email`), `recipient_key`, `user_id?`, `telegram_link_id?`, `open_token` (unique, ngẫu nhiên 32 byte, lưu dạng hash) |
| `report_opens` | `id`, `recipient_id`, `opened_at`, `via` (`email_link`, `telegram_button`, `portal`) |

Unique (`tenant_id`, `period_start`) cho báo cáo khác `superseded`.

### 4.2 Dựng (FR-REP-01)

Job `weekly_report` của Dagster (spec 04 mục 3.3) gọi `POST /v1/internal/reports/build {tenant_id, period}`. API:

1. Gọi bộ máy chỉ số với ngữ cảnh nội bộ của khách, lấy đủ số cho các phần ở mục 4.3.
2. Ghi `snapshot`: mọi số, `version` của từng chỉ số, `data_as_of`, `run_id`, cảnh báo dữ liệu. Báo cáo về sau chỉ hiển thị từ `snapshot` (FR-REP-07, NFR-10).
3. Tạo bản `draft`. Nếu đã có bản `draft` cho cùng tuần thì thay `snapshot`, giữ `insight_md`.
4. Thông báo cho team "Báo cáo tuần của <khách> đã sẵn sàng để viết nhận định".

### 4.3 Nội dung

**Gói Seller (FR-REP-02)**

1. Ba số chính (spec 03 mục 5), mỗi số kèm thay đổi so với tuần trước.
2. Bảng lãi lỗ tuần: `net_revenue`, `cogs`, các nhóm phí, `contribution_margin`, `net_profit_after_fees`, `net_margin_pct`, so với tuần trước.
3. Top 5 SKU lãi nhất và top 5 SKU lỗ nhất theo `sku_profit`.
4. `return_rate`, `cancel_rate` và thay đổi.
5. Cảnh báo dữ liệu: SKU thiếu giá vốn, doanh thu tạm tính, dữ liệu cũ.
6. Nhận định và việc cần làm (do người viết).

**Gói Agency (FR-REP-03)**

1. Ba số chính.
2. Chi tiêu theo nền tảng và thay đổi so với tuần trước.
3. Tiến độ ngân sách tháng theo nền tảng.
4. `roas_platform` theo nền tảng so với `roas_blended`.
5. `acos`, `tacos` khi có Amazon.
6. Chiến dịch cần chú ý: cờ đang bật (spec 03 mục 7), và trong 10 chiến dịch chi nhiều nhất tuần, các chiến dịch có `roas_platform` giảm quá ngưỡng `roas_drop_pct` so với trung bình 4 tuần trước.
7. Cảnh báo dữ liệu.
8. Nhận định và việc cần làm.

### 4.4 Viết nhận định và duyệt (FR-REP-04)

- `/ops/reports`: danh sách báo cáo theo trạng thái, lọc theo khách.
- `/ops/reports/[id]`: xem trước đúng như khách sẽ thấy; ô nhận định (Markdown, tối đa 2.000 ký tự); danh sách việc cần làm (tối đa 5, mỗi việc một dòng); nút "Duyệt và gửi".
- Nút duyệt bị khóa khi ô nhận định trống; API cũng từ chối (`422 INSIGHT_REQUIRED`).
- Từ giai đoạn 2, ô nhận định có sẵn bản nháp từ agent `weekly-insight` (spec 09); vẫn phải bấm duyệt.
- Sau khi duyệt, báo cáo không sửa được. Sửa sai bằng cách tạo bản mới cho cùng tuần (`POST /v1/reports/{id}/supersede`), bản cũ chuyển `superseded`.

### 4.5 Gửi (FR-REP-05)

1. `POST /v1/reports/{id}/approve` đặt `approved`, phát `report.ready`.
2. Trung tâm thông báo (spec 04 mục 5) tạo `report_recipients` cho mỗi người nhận theo kênh, mỗi người một `open_token`, rồi gửi mẫu `report_ready`.
3. Nội dung tin (cùng dữ liệu cho mọi kênh):

```
📊 Báo cáo tuần 41 (06/10–12/10) – Shop Demo

Doanh thu thực nhận: 152.340.000 ₫ (▲ 8,7%)
Lãi sau phí: 18.200.000 ₫ (▼ 9,4%)
Lãi so với tuần trước: −9,4%

[Xem báo cáo]  →  https://app.dataxland.vn/r/<open_token>
```

   Telegram: nút inline "Xem báo cáo" trỏ tới `/r/<open_token>`. Email: tiêu đề "Báo cáo tuần 41 – Shop Demo", cùng nội dung, có nút.
4. Trạng thái `sent` khi mọi người nhận đã gửi được; `partially_sent` khi có kênh lỗi sau khi hết lượt thử lại. Mục tiêu: gửi trong 10 phút sau khi duyệt.

### 4.6 Ghi nhận mở (FR-REP-06)

- `GET /r/{token}`: tìm người nhận theo hash của token, ghi `report_opens` (`via` theo kênh của người nhận), rồi chuyển hướng tới `/app/reports/<id>?t=<tenant_id>`. Token sai → trang thông báo chung, không lộ thông tin.
- Việc mở được ghi ngay cả khi người nhận chưa đăng nhập; xem nội dung vẫn cần đăng nhập.
- Mở trực tiếp trong cổng ghi `via = portal` cho người dùng đó (một lần mỗi ngày).
- Màn hình vận hành hiện theo từng báo cáo: số người nhận, đã mở, mở lần đầu lúc nào, qua kênh nào.

### 4.7 Lưu trữ (FR-REP-07)

- `/app/reports`: danh sách các tuần đã gửi, mới nhất trước.
- `/app/reports/[id]`: hiển thị từ `snapshot`, kèm "Số liệu tại thời điểm <data_as_of>, chỉ số phiên bản …". Không gọi lại bộ máy chỉ số.

### 4.8 Endpoint

| Method | Đường dẫn | Quyền |
|---|---|---|
| `GET` | `/v1/reports` | `reports.read`; khách chỉ thấy báo cáo đã gửi, nhân viên thấy mọi trạng thái |
| `GET` | `/v1/reports/{id}` | `reports.read` |
| `GET` | `/v1/reports/latest` | `reports.read`; dùng cho `/report` của bot |
| `PUT` | `/v1/reports/{id}` | `reports.edit`; sửa `insight_md`, `actions` khi `draft` |
| `POST` | `/v1/reports/{id}/approve` | `reports.approve` |
| `POST` | `/v1/reports/{id}/supersede` | `reports.approve` |
| `POST` | `/v1/reports/{id}/resend` | `reports.approve`; gửi lại cho người nhận bị lỗi |
| `GET` | `/v1/reports/{id}/opens` | `ops.read` |

FR-AGY-03 (báo cáo gộp nhiều shop cho agency) ở giai đoạn 2.

## 5. Sổ tay chỉ số (FR-DSH-04)

- `/app/metrics`: danh sách chỉ số khách được xem (`GET /v1/metrics`), nhóm theo gói, có ô tìm kiếm theo `name_vi` và `synonyms_vi`.
- `/app/metrics/[metric]`: tên, mô tả, công thức diễn giải, nguồn, đơn vị, chiều cắt được, phiên bản hiện tại, lịch sử thay đổi.
- Không có nội dung viết tay; mọi thứ từ `handbook.json` qua API.

## 6. Nhập liệu (giao diện cho FR-INP-01..04)

- `/app/inputs/costs`: bảng giá vốn theo SKU (lọc, sửa trực tiếp, thêm dòng với ngày hiệu lực), nút tải mẫu Excel, nút tải file lên. Kết quả tải file hiện số dòng nhận, số dòng lỗi và bảng lỗi (dòng, cột, lý do).
- Đầu trang có hộp "SKU chưa có giá vốn" từ `GET /v1/inputs/product-costs/missing`, sắp theo doanh thu, có nút điền nhanh.
- Ghi chú dưới bảng: "Giá vốn mới sẽ được áp dụng sau lần cập nhật dữ liệu kế tiếp (khoảng 10–20 phút)."
- `/app/inputs/budgets`: lưới tháng × nền tảng, sửa trực tiếp. Hiện cho khách gói Agency, và cho khách gói Seller có nguồn quảng cáo.

## 7. Nhật ký quyết định (FR-DEC-01..02)

### 7.1 Dữ liệu

`decisions`: `id`, `tenant_id`, `decided_on` (date), `title`, `detail_md`, `decided_by` (tên người quyết, chuỗi), `metric`, `metric_version`, `dimension_filter` jsonb, `baseline_window` (`last_7_days` \| `last_28_days`), `baseline_value`, `target_value`, `remeasure_on` (date), `after_value`, `after_measured_at`, `conclusion` (`achieved`, `not_achieved`, `inconclusive`), `conclusion_md`, `created_by`.

### 7.2 Hành vi

- Tạo quyết định (FR-DEC-01): chọn chỉ số từ thư viện; API tự lấy `baseline_value` qua bộ máy chỉ số cho cửa sổ trước `decided_on`, ghi kèm `metric_version`. Phát `decision.logged`.
- Đến `remeasure_on` (FR-DEC-02): job `decision_reminders` phát `decision.remeasure_due`; team nhận nhắc qua nhóm Telegram nội bộ và email. Team mở quyết định, bấm "Lấy giá trị hiện tại" (API tính lại với cùng cửa sổ độ dài sau ngày quyết định) hoặc nhập tay, rồi chọn kết luận.
- FR-DEC-03 (tự lấy giá trị sau) và FR-DEC-04 (báo cáo giá trị cuối kỳ) ở giai đoạn sau.

### 7.3 Endpoint

| Method | Đường dẫn | Quyền |
|---|---|---|
| `GET` | `/v1/decisions` | `decisions.read` |
| `POST` | `/v1/decisions` | `decisions.write` |
| `GET` | `/v1/decisions/{id}` | `decisions.read` |
| `PUT` | `/v1/decisions/{id}` | `decisions.write`; sửa nội dung, `after_value`, kết luận |
| `POST` | `/v1/decisions/{id}/measure` | `decisions.write`; tính `after_value` qua bộ máy chỉ số |

## 8. Trang agency (FR-AGY-01..02)

- `GET /v1/partner/tenants` (vai trò `partner`): với mỗi khách có `partner_grants` đang hiệu lực cho agency của người gọi, API gọi bộ máy chỉ số **riêng cho từng khách** (mỗi lần một `AuthContext`), trả `{tenant_id, name, ad_spend_mtd, budget_pacing, roas_blended, flags: [...]}`. Không truy vấn nào đọc hai khách cùng lúc.
- `/partner`: bảng các shop, sắp theo số cờ rồi chi tiêu; mỗi dòng bấm vào được.
- `/partner/[tenant]`: dashboard gói Agency (mục 3.2) với `X-Tenant-Id` của shop đó.
- Shop thu quyền thì dòng đó biến mất ở lần tải kế tiếp; gọi trực tiếp bị 403.

## 9. Cài đặt

- `/app/settings/members` (owner): mời, gỡ, chọn chỉ số cho member (spec 05 mục 5.1).
- `/app/settings/partners` (owner): danh sách agency trong `partners`, cấp và thu quyền (spec 05 mục 5.3).
- `/app/settings/telegram`: tạo mã liên kết cho chat riêng (mọi người dùng) hoặc nhóm (owner, chọn phạm vi chỉ số); hiện mã, link `https://t.me/<bot>?start=<mã>`, thời hạn đếm ngược 10 phút; danh sách liên kết và nút gỡ (spec 08).
- Trang Telegram ghi rõ: "Tin nhắn qua Telegram được lưu trên máy chủ của Telegram. Báo cáo luôn được gửi cả qua email." (NFR-11, NFR-12)

## 10. Màn hình vận hành (FR-OPS-04)

| Trang | Nội dung |
|---|---|
| `/ops` | Bảng một dòng mỗi khách từ `GET /v1/ops/overview`: tên, gói, trạng thái; mỗi nguồn một ô màu (xanh: thành công trong `freshness_hours`; vàng: trễ; đỏ: lỗi) kèm thời điểm; số test chặn và cảnh báo đang lỗi; báo cáo tuần (chưa dựng, nháp, đã duyệt, đã gửi, số người đã mở/tổng). Tự làm mới mỗi 60 giây |
| `/ops/tenants/[id]` | Cấu hình đã đồng bộ (chỉ đọc), nguồn và nút kết nối OAuth, lịch sử chạy, chi tiết lỗi chặn (bảng dòng lỗi của test đối soát), nút chạy lại |
| `/ops/reports`, `/ops/reports/[id]` | Mục 4.4 |
| `/ops/health-checks` | Spec 07 |

Giai đoạn 2 thêm cột chi phí và giờ người (FR-OPS-06) và hàng chờ ghép định danh (spec 10).

## 11. Kiểm thử

- `vitest`: định dạng tiền, phần trăm, ROAS, tuần; tạo CSV có BOM.
- Playwright (`make e2e`) trên stack local với emulator:

| Kịch bản | FR |
|---|---|
| Owner `demo_seller` đăng nhập, xem dashboard Seller, mọi khối có số và thời điểm cập nhật | FR-DSH-01, FR-DSH-03 |
| Bấm tên chỉ số mở định nghĩa sổ tay | FR-DSH-03, FR-DSH-04 |
| Xuất CSV khối lãi theo SKU, file đúng cột | FR-DSH-05 |
| Tải file giá vốn có dòng lỗi, thấy bảng lỗi đúng dòng | FR-INP-02 |
| Data lead dựng báo cáo, nút duyệt khóa khi trống nhận định, viết rồi duyệt, adapter thông báo giả lập nhận tin có ba số và link | FR-REP-01, FR-REP-04, FR-REP-05 |
| Mở link `/r/<token>`, màn hình vận hành hiện đã mở | FR-REP-06 |
| Sửa dữ liệu mẫu và chạy lại pipeline, báo cáo cũ vẫn hiện số cũ | FR-REP-07 |
| Người dùng agency thấy `demo_agency` khi được cấp, mất khi bị thu | FR-AGY-01, FR-AGY-02, FR-AUTH-04 |
| Tạo quyết định, giá trị lúc quyết định tự điền | FR-DEC-01 |

## 12. Tiêu chí hoàn thành

- Mọi trang ở mục 1 (trừ `ask`) chạy với hai khách giả lập.
- Báo cáo tuần đi trọn vòng dựng → viết nhận định → duyệt → gửi Telegram và email → ghi nhận mở trên `dev`.
- Mọi kịch bản Playwright ở mục 11 qua.
