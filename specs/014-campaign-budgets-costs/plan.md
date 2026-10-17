# Implementation Plan: Ngân sách theo chiến dịch, chi phí theo khách

**Branch**: `014-campaign-budgets-costs` | **Spec**: [spec.md](spec.md)

- Alembic `0002`: `ad_budgets.campaign_id`, chỉ mục duy nhất gồm chiến dịch. API `/v1/inputs/ad-budgets` nhận `campaign_id`, chặn trộn hai mức; `/v1/inputs/ad-campaigns` qua bộ máy chỉ số.
- Connector `portal` xuất `campaign_id`; `stg_portal__ad_budgets`, `dim_ad_budget`, mart `mrt_agency__budget_campaign_monthly`; dữ liệu mẫu TikTok Ads tháng 10 của `demo_agency` nhập theo chiến dịch.
- Semantic: biến thể cho `budget`, `spend_mtd`, `budget_expected`; chiều `campaign`, `campaign_name` cho chỉ số ngân sách.
- Job Dagster `gcp_costs`; router `costs.py` (nội bộ, màn vận hành, chia hóa đơn, giờ người); web `/ops/costs`.

Quyết định: ADR 0002 #55–#56.
