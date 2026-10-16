{#- Ghép mọi `stg_<source>__fees` đang bật (spec 02 §1.3). Thêm nguồn mới chỉ cần thêm thư mục staging. -#}
{{ config(materialized='table') }}

{{ dx_union_enabled('fees', dx_contract('fees')) }}
