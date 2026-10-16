{{ config(enabled='amazon_seller' in var('sources', [])) }}
with li as (
    select * from (
        select *, row_number() over (partition by amazon_order_id, order_item_id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'amazon_seller__order_items') }}
    ) as src where rn = 1
),

o as (
    select amazon_order_id, purchase_date from (
        select *, row_number() over (partition by amazon_order_id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'amazon_seller__orders') }}
    ) as x where rn = 1
),

l as (
    select li.*, {{ dx_vn_date(dx_ts('o.purchase_date')) }} as order_date
    from li inner join o on o.amazon_order_id = li.amazon_order_id
)

select
    cast('amazon_seller' as {{ dbt.type_string() }}) as source,
    {{ dbt.concat([dx_str('l.amazon_order_id'), "'-'", dx_str('l.order_item_id')]) }} as source_id,
    {{ dx_str('l.amazon_order_id') }} as order_source_id,
    trim({{ dx_str('l.seller_sku') }}) as seller_sku,
    {{ dx_str('l.title') }} as item_name,
    cast(l.quantity_ordered as bigint) as quantity,
    {{ to_vnd(dx_div(dx_num('l.item_price_amount'), 'l.quantity_ordered'), dx_str('l.currency'), 'l.order_date') }} as unit_price_vnd,
    {{ to_vnd(dx_num('l.item_price_amount'), dx_str('l.currency'), 'l.order_date') }} as line_gross_vnd,
    {{ to_vnd('coalesce(' ~ dx_num('l.promotion_discount_amount') ~ ', 0)', dx_str('l.currency'), 'l.order_date') }} as allocated_discount_vnd
from l
{{ dx_fx_join(dx_str('l.currency'), 'l.order_date') }}
