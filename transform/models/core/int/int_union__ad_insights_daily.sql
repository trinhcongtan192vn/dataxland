{#- Ghép mọi `stg_<source>__ad_insights_daily` đang bật (spec 02 §1.3). Thêm nguồn mới chỉ cần thêm thư mục staging. -#}
{{ config(materialized='table') }}

{{ dx_union_enabled('ad_insights_daily', dx_contract('ad_insights_daily')) }}
