# Runbook – Kết nối Windsor.ai (FR-ING-04, spec 01 §8)

Hướng dẫn từng bước có hình ở cổng: `/ops/integrations/windsor` (nội dung: `knowledge/integrations/windsor.md`).

Tóm tắt:

1. Đăng nhập Windsor.ai bằng tài khoản công ty. Thêm connector cho nguồn (Meta Ads, TikTok Ads, Google Ads, Amazon Ads,
   Amazon Seller Central) và đăng nhập tài khoản quảng cáo của khách (khách cấp quyền).
2. Chọn đích BigQuery, project `dataxland-prod`, dataset `t_<tenant_id>_raw` (hoặc `t_<tenant_id>_windsor` nếu Windsor
   không cho đặt tên bảng – khi đó chạy lại `ops/bootstrap_tenant.py` để tạo view đúng hợp đồng).
3. Tên bảng: `<source>__ad_insights_daily` (quảng cáo) hoặc `amazon_seller__orders`, `__order_items`,
   `__financial_events`, `__daily_totals`. Trường tối thiểu: `date, account_id, campaign_id, campaign_name, adgroup_id,
   adgroup_name, spend, currency, impressions, clicks, conversions, conversion_value`.
4. Lịch đồng bộ: 3 giờ cho gói Agency, 6 giờ cho gói Seller.
5. Ghi `account_id` vào `tenants/<id>.yml` (`connector: windsor`).
6. Kiểm tra: bước `check_windsor_freshness` ở `/ops/tenants/<id>` xanh; chi tiêu theo ngày khớp giao diện nền tảng.
