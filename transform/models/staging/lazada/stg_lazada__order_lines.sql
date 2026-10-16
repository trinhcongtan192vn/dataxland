{{ config(enabled='lazada' in var('sources', [])) }}
with li as (
    select * from (
        select *, row_number() over (partition by order_item_id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'lazada__order_items') }}
    ) as src where rn = 1
),

o as (
    select order_id, currency, created_at from (
        select *, row_number() over (partition by order_id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'lazada__orders') }}
    ) as x where rn = 1
),

l as (
    select li.*, o.currency, {{ dx_vn_date(dx_from_local_vn(dx_str('o.created_at'))) }} as order_date
    from li inner join o on {{ dx_str('o.order_id') }} = {{ dx_str('li.order_id') }}
)

select
    cast('lazada' as {{ dbt.type_string() }}) as source,
    {{ dx_str('l.order_item_id') }} as source_id,
    {{ dx_str('l.order_id') }} as order_source_id,
    trim({{ dx_str('l.sku') }}) as seller_sku,
    {{ dx_str('l.name') }} as item_name,
    cast(1 as bigint) as quantity,
    {{ to_vnd('l.paid_price', 'l.currency', 'l.order_date') }} as unit_price_vnd,
    {{ to_vnd('l.item_price', 'l.currency', 'l.order_date') }} as line_gross_vnd,
    {{ to_vnd('coalesce(' ~ dx_num('l.voucher_seller') ~ ', 0)', 'l.currency', 'l.order_date') }} as allocated_discount_vnd
from l
{{ dx_fx_join('l.currency', 'l.order_date') }}
