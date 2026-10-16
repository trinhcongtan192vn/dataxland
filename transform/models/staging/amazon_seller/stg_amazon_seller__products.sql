{{ config(enabled='amazon_seller' in var('sources', [])) }}
{#- Amazon không có bảng sản phẩm riêng qua Windsor: lấy SKU và tên từ dòng đơn. -#}
with li as (
    select seller_sku, title, asin, row_number() over (partition by seller_sku order by _dx_loaded_at desc) as rn
    from {{ source('raw', 'amazon_seller__order_items') }}
)

select
    cast('amazon_seller' as {{ dbt.type_string() }}) as source,
    {{ dx_str('asin') }} as source_id,
    trim({{ dx_str('seller_sku') }}) as seller_sku,
    {{ dx_str('title') }} as name,
    cast(null as {{ dbt.type_string() }}) as barcode,
    cast(null as {{ dbt.type_string() }}) as category_raw
from li
where rn = 1
