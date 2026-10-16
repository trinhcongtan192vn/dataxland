{#- Ghép mọi `stg_<source>__order_lines` đang bật (spec 02 §1.3). Thêm nguồn mới chỉ cần thêm thư mục staging. -#}
{{ config(materialized='table') }}

{{ dx_union_enabled('order_lines', dx_contract('order_lines')) }}
