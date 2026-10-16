{#- Ghép mọi `stg_<source>__products` đang bật (spec 02 §1.3). Thêm nguồn mới chỉ cần thêm thư mục staging. -#}
{{ config(materialized='table') }}

{{ dx_union_enabled('products', dx_contract('products')) }}
