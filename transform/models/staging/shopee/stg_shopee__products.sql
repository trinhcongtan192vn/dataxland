{{ config(enabled='shopee' in var('sources', [])) }}
with p as (
    select * from (
        select *, row_number() over (partition by item_id, model_id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'shopee__products') }}
    ) as src where rn = 1
)

select
    cast('shopee' as {{ dbt.type_string() }}) as source,
    {{ dbt.concat([dx_str('item_id'), "'-'", dx_str('model_id')]) }} as source_id,
    trim(coalesce(nullif({{ dx_str('model_sku') }}, ''), {{ dx_str('item_sku') }})) as seller_sku,
    {{ dx_str('item_name') }} as name,
    {{ dx_str('gtin_code') }} as barcode,
    {{ dx_str('category_name') }} as category_raw
from p
