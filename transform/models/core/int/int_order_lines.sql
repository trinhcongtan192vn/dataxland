{#- Dòng đơn gắn sản phẩm và giá vốn hiệu lực tại ngày đặt (FR-INP-01, spec 02 §4.1). -#}
{{ config(materialized='table') }}

with l as (
    select * from {{ ref('int_union__order_lines') }}
),

o as (
    select order_id, channel_id, source, source_id, order_date from {{ ref('int_orders') }}
),

keyed as (
    select
        l.*,
        o.order_id,
        o.channel_id,
        o.order_date,
        lower(trim(l.seller_sku)) as sku_key,
        case
            when nullif(trim(l.seller_sku), '') is not null then {{ dbt_utils.generate_surrogate_key(['lower(trim(l.seller_sku))']) }}
            else {{ dbt_utils.generate_surrogate_key(['l.source', 'l.source_id']) }}
        end as base_product_id
    from l
    inner join o on o.source = l.source and o.source_id = l.order_source_id
)

select
    {{ dbt_utils.generate_surrogate_key(['k.source', 'k.source_id']) }} as order_line_id,
    k.order_id,
    k.channel_id,
    k.order_date,
    k.source,
    k.source_id,
    coalesce(ip.canonical_id, k.base_product_id) as product_id,
    k.seller_sku,
    k.item_name,
    k.quantity,
    k.unit_price_vnd,
    k.line_gross_vnd,
    k.allocated_discount_vnd,
    cast(k.line_gross_vnd - k.allocated_discount_vnd as numeric) as line_net_vnd,
    c.unit_cost_vnd,
    cast(k.quantity * c.unit_cost_vnd as numeric) as cogs_vnd,
    (c.unit_cost_vnd is null) as has_missing_cogs
from keyed as k
left join {{ ref('int_identity__product') }} as ip on ip.sku_key = k.sku_key
left join {{ ref('dim_product_cost') }} as c
    on c.sku_key = k.sku_key
    and k.order_date >= c.valid_from
    and (c.valid_to is null or k.order_date <= c.valid_to)
