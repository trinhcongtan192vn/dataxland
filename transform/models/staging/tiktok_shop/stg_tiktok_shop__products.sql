{{ config(enabled='tiktok_shop' in var('sources', [])) }}
with p as (
    select * from (
        select *, row_number() over (partition by product_id, sku_id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'tiktok_shop__products') }}
    ) as src where rn = 1
)

select
    cast('tiktok_shop' as {{ dbt.type_string() }}) as source,
    {{ dbt.concat([dx_str('product_id'), "'-'", dx_str('sku_id')]) }} as source_id,
    trim({{ dx_str('seller_sku') }}) as seller_sku,
    {{ dx_str('title') }} as name,
    {{ dx_str('barcode') }} as barcode,
    {{ dx_str('category_name') }} as category_raw
from p
