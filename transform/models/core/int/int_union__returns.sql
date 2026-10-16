{#- Ghép mọi `stg_<source>__returns` đang bật (spec 02 §1.3). Thêm nguồn mới chỉ cần thêm thư mục staging. -#}
{{ config(materialized='table') }}

{{ dx_union_enabled('returns', dx_contract('returns')) }}
