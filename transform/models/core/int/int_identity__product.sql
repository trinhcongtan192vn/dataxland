{#- Cặp ghép sản phẩm đã duyệt (spec 10 §7): SKU chuẩn hóa → canonical_id. Bảng trống ở GĐ1. -#}
{{ config(materialized='table') }}

select
    lower(trim(p.seller_sku)) as sku_key,
    min(m.canonical_id) as canonical_id
from {{ source('identity', 'identity_map') }} as m
inner join {{ ref('int_union__products') }} as p
    on p.source = m.source and p.source_id = m.source_id
where m.entity = 'product' and nullif(trim(p.seller_sku), '') is not null
group by 1
