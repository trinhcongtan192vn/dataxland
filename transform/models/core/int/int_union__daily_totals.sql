{#- Ghép mọi `stg_<source>__daily_totals` đang bật (spec 02 §1.3). Thêm nguồn mới chỉ cần thêm thư mục staging. -#}
{{ config(materialized='table') }}

{{ dx_union_enabled('daily_totals', dx_contract('daily_totals')) }}
