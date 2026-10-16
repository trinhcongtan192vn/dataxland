{#- Ngày × kênh bán (spec 02 §5). `amazon_ad_sales_vnd`: doanh thu quảng cáo Amazon trong ngày, ghi trên dòng
kênh Amazon Seller (dùng cho ACOS). -#}
with o as (
    select o.*, r.net_revenue_vnd, r.is_returned
    from {{ ref('fct_order') }} as o
    inner join {{ ref('int_order_revenue') }} as r on r.order_id = o.order_id
),

ch as (
    select channel_id, platform, row_number() over (partition by platform order by channel_id) as rn
    from {{ ref('dim_channel') }}
),

amz as (
    select a.date, sum(a.conversion_value_vnd) as v
    from {{ ref('fct_ad_performance_daily') }} as a
    where a.source = 'amazon_ads'
    group by a.date
),

g as (
    select
        o.order_date as date,
        o.channel_id,
        count(case when not o.is_cancelled then 1 end) as order_count,
        cast(sum(o.gross_amount_vnd) as numeric) as gross_amount_vnd,
        cast(sum(o.net_revenue_vnd) as numeric) as net_revenue_vnd,
        count(case when o.is_cancelled then 1 end) as cancelled_count,
        count(case when o.is_returned then 1 end) as returned_count
    from o
    group by o.order_date, o.channel_id
)

select
    {{ dbt_utils.generate_surrogate_key(['g.channel_id', dx_str('g.date')]) }} as sales_daily_id,
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    g.date,
    g.channel_id,
    ch.platform,
    g.order_count,
    g.gross_amount_vnd,
    g.net_revenue_vnd,
    cast(case when ch.platform = 'amazon_seller' and ch.rn = 1 then coalesce(amz.v, 0) else 0 end as numeric) as amazon_ad_sales_vnd,
    g.cancelled_count,
    g.returned_count
from g
left join ch on ch.channel_id = g.channel_id
left join amz on amz.date = g.date
