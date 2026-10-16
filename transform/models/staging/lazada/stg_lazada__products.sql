{{ config(enabled='lazada' in var('sources', [])) }}
with p as (
    select * from (
        select *, row_number() over (partition by item_id, sku_id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'lazada__products') }}
    ) as src where rn = 1
)

select
    cast('lazada' as {{ dbt.type_string() }}) as source,
    {{ dbt.concat([dx_str('item_id'), "'-'", dx_str('sku_id')]) }} as source_id,
    trim({{ dx_str('seller_sku') }}) as seller_sku,
    {{ dx_str('name') }} as name,
    {{ dx_str('ean_code') }} as barcode,
    {{ dx_str('primary_category') }} as category_raw
from p
