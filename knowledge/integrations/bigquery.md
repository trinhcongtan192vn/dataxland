# Google Cloud: BigQuery và Secret Manager

Kho dữ liệu ở `dev`/`prod` là BigQuery; bí mật nằm ở Secret Manager (spec 00 §4, spec 04 §2).

## 1. Project và API

1. Tạo GCP project cho từng môi trường (ví dụ `dataxland-dev`, `dataxland-prod`), gắn billing.
2. Bật API: BigQuery, Secret Manager, IAM, IAM Credentials, Cloud Storage, Artifact Registry.
3. Biến: `GCP_PROJECT_ID=<project>`, `BQ_LOCATION=asia-southeast1`.

## 2. Service account

| Service account | Vai trò | Dùng cho |
|---|---|---|
| `dx-dagster@` | `BigQuery Job User`, `Secret Manager Secret Accessor`, `Service Account Token Creator` trên các `dxt-*` | Dagster, dbt, connector |
| `dx-api@` | `Secret Manager Secret Accessor` + `Secret Version Adder` (ghi token sàn), `Firebase Authentication Admin` | API |
| `dx-cube@` | `BigQuery Data Viewer` trên dataset `*_marts`, `BigQuery Job User` | Cube |
| `dxt-<tenant>@` | Tạo tự động khi `ops/bootstrap_tenant.py` chạy; chỉ đọc/ghi dataset của khách đó | Truy vấn theo khách |

Trên VM, gắn service account bằng Workload Identity hoặc file khóa đặt ngoài repo, trỏ `GOOGLE_APPLICATION_CREDENTIALS` tới file đó.

## 3. Kiểm tra

- `make dbt-build TENANT=demo_seller` trên `dev` tạo `t_demo_seller_marts`.
- `gcloud secrets list` thấy các secret `dx-*`.

## 4. Chi phí theo khách (FR-OPS-06)

1. Trong Google Cloud Console mở **Billing → Billing export → BigQuery export**, bật **Standard usage cost**, chọn
   project `dataxland-<env>` và dataset `billing_export` (tạo mới nếu chưa có).
2. Chờ GCP tạo bảng `gcp_billing_export_v1_<BILLING_ACCOUNT_ID>` (vài giờ sau khi bật).
3. Đặt biến môi trường `GCP_BILLING_EXPORT_TABLE=<project>.billing_export.gcp_billing_export_v1_<ID>` cho Dagster.
4. Cấp cho `dx-dagster@` quyền `BigQuery Data Viewer` trên dataset `billing_export`.
5. Job `gcp_costs` chạy 6:00 mỗi ngày, cộng chi phí theo nhãn `tenant_id` (dataset và job BigQuery đều gắn nhãn này)
   rồi ghi vào màn **Vận hành → Chi phí**. Chi phí không có nhãn khách (hạ tầng dùng chung) không chia cho khách.
6. Hóa đơn Windsor và Claude: cuối tháng nhập số tiền ở màn **Chi phí**, bấm "Chia cho khách".
