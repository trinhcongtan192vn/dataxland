{#- Ghép mọi `stg_<source>__orders` đang bật (spec 02 §1.3). Thêm nguồn mới chỉ cần thêm thư mục staging. -#}
{{ config(materialized='table') }}

{{ dx_union_enabled('orders', dx_contract('orders')) }}
