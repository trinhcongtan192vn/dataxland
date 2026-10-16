{{ config(enabled='shopee' in var('sources', [])) }}
{#- Dòng đơn Shopee. Giảm giá của shop (voucher) phân bổ xuống dòng theo tỷ lệ giá trị dòng. -#}
with li as (
    select * from (
        select *, row_number() over (partition by order_sn, item_id, model_id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'shopee__order_items') }}
    ) as src where rn = 1
),

o as (
    select * from (
        select *, row_number() over (partition by order_sn order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'shopee__orders') }}
    ) as o2 where rn = 1
),

lines as (
    select
        li.*,
        {{ dx_vn_date(dx_from_unix('o.create_time')) }} as order_date,
        {{ dx_str('o.currency') }} as currency,
        coalesce({{ dx_num('o.seller_voucher') }}, 0) as voucher,
        {{ dx_num('li.model_original_price') }} * li.model_quantity_purchased as gross_o,
        {{ dx_num('li.model_discounted_price') }} * li.model_quantity_purchased as disc_price_o,
        sum({{ dx_num('li.model_discounted_price') }} * li.model_quantity_purchased)
            over (partition by li.order_sn) as order_disc_total
    from li
    inner join o on o.order_sn = li.order_sn
),

priced as (
    select
        lines.*,
        (gross_o - disc_price_o) + voucher * {{ dx_div('disc_price_o', 'order_disc_total') }} as alloc_disc_o
    from lines
)

select
    cast('shopee' as {{ dbt.type_string() }}) as source,
    {{ dbt.concat([dx_str('p.order_sn'), "'-'", dx_str('p.item_id'), "'-'", dx_str('p.model_id')]) }} as source_id,
    {{ dx_str('p.order_sn') }} as order_source_id,
    trim(coalesce(nullif({{ dx_str('p.model_sku') }}, ''), {{ dx_str('p.item_sku') }})) as seller_sku,
    {{ dx_str('p.item_name') }} as item_name,
    cast(p.model_quantity_purchased as bigint) as quantity,
    {{ to_vnd('p.model_discounted_price', 'p.currency', 'p.order_date') }} as unit_price_vnd,
    {{ to_vnd('p.gross_o', 'p.currency', 'p.order_date') }} as line_gross_vnd,
    {{ to_vnd('coalesce(' ~ dx_num('p.alloc_disc_o') ~ ', 0)', 'p.currency', 'p.order_date') }} as allocated_discount_vnd
from priced as p
{{ dx_fx_join('p.currency', 'p.order_date') }}
