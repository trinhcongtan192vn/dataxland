{{ config(enabled=var('pack') in ['seller']) }}
{#- Một dòng đơn; doanh thu thực nhận và các phí của đơn phân bổ xuống dòng theo tỷ lệ doanh thu dòng (spec 02 §5). -#}
with l as (
    select * from {{ ref('fct_order_line') }}
),

o as (
    select * from {{ ref('mrt_seller__orders') }} where row_type = 'order'
),

tot as (
    select order_id, sum(line_net_vnd) as tot_net, count(*) as n
    from l
    group by order_id
),

s as (
    select
        l.*,
        case when coalesce(tot.tot_net, 0) = 0 then 1.0 / cast(tot.n as {{ dbt.type_float() }})
            else cast(l.line_net_vnd as {{ dbt.type_float() }}) / cast(tot.tot_net as {{ dbt.type_float() }}) end as share
    from l
    inner join tot on tot.order_id = l.order_id
)

select
    s.order_line_id,
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    s.order_id,
    o.order_date,
    o.channel_id,
    o.platform,
    s.product_id,
    s.seller_sku,
    p.canonical_name as product_name,
    s.quantity,
    cast(o.net_revenue_vnd * s.share as numeric) as net_revenue_vnd,
    cast(o.platform_fee_vnd * s.share as numeric) as platform_fee_vnd,
    cast(o.payment_fee_vnd * s.share as numeric) as payment_fee_vnd,
    cast(o.shipping_cost_vnd * s.share as numeric) as shipping_cost_vnd,
    cast(o.allocated_ad_spend_vnd * s.share as numeric) as allocated_ad_spend_vnd,
    cast(o.other_cost_vnd * s.share as numeric) as other_cost_vnd,
    cast(o.return_cost_vnd * s.share as numeric) as return_cost_vnd,
    cast(case when o.status in ('cancelled', 'failed_delivery') then 0 else coalesce(s.cogs_vnd, 0) end as numeric) as cogs_vnd,
    s.has_missing_cogs,
    o.is_cancelled,
    o.is_returned,
    o.is_provisional,
    o.status
from s
inner join o on o.order_id = s.order_id
left join {{ ref('dim_product') }} as p on p.product_id = s.product_id
