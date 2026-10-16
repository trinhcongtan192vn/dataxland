{{ config(enabled='tiktok_shop' in var('sources', [])) }}
{#- Dòng đơn TikTok Shop: mỗi đơn vị một dòng. -#}
with li as (
    select * from (
        select *, row_number() over (partition by id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'tiktok_shop__order_items') }}
    ) as src where rn = 1
),

o as (
    select id, currency, create_time from (
        select *, row_number() over (partition by id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'tiktok_shop__orders') }}
    ) as x where rn = 1
),

l as (
    select li.*, o.currency, {{ dx_vn_date(dx_from_unix('o.create_time')) }} as order_date
    from li inner join o on o.id = li.order_id
)

select
    cast('tiktok_shop' as {{ dbt.type_string() }}) as source,
    {{ dx_str('l.id') }} as source_id,
    {{ dx_str('l.order_id') }} as order_source_id,
    trim({{ dx_str('l.seller_sku') }}) as seller_sku,
    {{ dx_str('l.product_name') }} as item_name,
    cast(coalesce(l.quantity, 1) as bigint) as quantity,
    {{ to_vnd('l.sale_price', 'l.currency', 'l.order_date') }} as unit_price_vnd,
    {{ to_vnd('l.original_price * coalesce(l.quantity, 1)', 'l.currency', 'l.order_date') }} as line_gross_vnd,
    {{ to_vnd('coalesce(l.seller_discount, 0) * coalesce(l.quantity, 1)', 'l.currency', 'l.order_date') }} as allocated_discount_vnd
from l
{{ dx_fx_join('l.currency', 'l.order_date') }}
