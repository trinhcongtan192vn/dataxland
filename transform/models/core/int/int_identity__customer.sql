{#- Cặp ghép người mua đã duyệt theo quy tắc (spec 10 §3, §7): đơn → canonical_id (dạng băm). -#}
{{ config(materialized='table') }}

select
    m.source,
    m.source_id,
    min(m.canonical_id) as canonical_id
from {{ source('identity', 'identity_map') }} as m
where m.entity = 'customer'
group by 1, 2
