{{ config(enabled=var('pack') in ['seller']) }}
{#- Một đơn (row_type = 'order') cộng các dòng chi phí không phân bổ được vào đơn nào (row_type = 'unallocated_cost'),
để tổng chi phí và lãi luôn đủ kể cả khi khách chọn `cost_allocation: none` (spec 02 §5). -#}
with o as (
    select * from {{ ref('fct_order') }}
),

rev as (
    select * from {{ ref('int_order_revenue') }}
),

alloc as (
    select
        order_id,
        cast(sum(case when cost_type = 'platform_fee' then allocated_amount_vnd else 0 end) as numeric) as platform_fee_vnd,
        cast(sum(case when cost_type = 'payment_fee' then allocated_amount_vnd else 0 end) as numeric) as payment_fee_vnd,
        cast(sum(case when cost_type = 'shipping' then allocated_amount_vnd else 0 end) as numeric) as shipping_cost_vnd,
        cast(sum(case when cost_type = 'ad_spend' then allocated_amount_vnd else 0 end) as numeric) as allocated_ad_spend_vnd,
        cast(sum(case when cost_type = 'other' then allocated_amount_vnd else 0 end) as numeric) as other_cost_vnd
    from {{ ref('fct_cost_allocated') }}
    where order_id is not null
    group by order_id
),

unalloc as (
    select
        cost_id, cost_date, channel_id,
        cast(sum(case when cost_type = 'platform_fee' then allocated_amount_vnd else 0 end) as numeric) as platform_fee_vnd,
        cast(sum(case when cost_type = 'payment_fee' then allocated_amount_vnd else 0 end) as numeric) as payment_fee_vnd,
        cast(sum(case when cost_type = 'shipping' then allocated_amount_vnd else 0 end) as numeric) as shipping_cost_vnd,
        cast(sum(case when cost_type = 'ad_spend' then allocated_amount_vnd else 0 end) as numeric) as allocated_ad_spend_vnd,
        cast(sum(case when cost_type = 'other' then allocated_amount_vnd else 0 end) as numeric) as other_cost_vnd
    from {{ ref('fct_cost_allocated') }}
    where order_id is null
    group by cost_id, cost_date, channel_id
),

ch as (
    select channel_id, platform from {{ ref('dim_channel') }}
)

select
    o.order_id,
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    cast('order' as {{ dbt.type_string() }}) as row_type,
    o.order_date,
    o.channel_id,
    ch.platform,
    o.status,
    o.is_provisional,
    o.customer_id,
    o.gross_amount_vnd,
    rev.net_revenue_vnd,
    coalesce(a.platform_fee_vnd, 0) as platform_fee_vnd,
    coalesce(a.payment_fee_vnd, 0) as payment_fee_vnd,
    coalesce(a.shipping_cost_vnd, 0) as shipping_cost_vnd,
    coalesce(a.allocated_ad_spend_vnd, 0) as allocated_ad_spend_vnd,
    coalesce(a.other_cost_vnd, 0) as other_cost_vnd,
    rev.return_fee_vnd as return_cost_vnd,
    cast(case when o.status in ('cancelled', 'failed_delivery') then 0 else o.cogs_known_vnd end as numeric) as cogs_vnd,
    o.has_missing_cogs,
    o.is_cancelled,
    rev.is_returned
from o
inner join rev on rev.order_id = o.order_id
left join alloc as a on a.order_id = o.order_id
left join ch on ch.channel_id = o.channel_id

union all

select
    {{ dbt.concat(["'unallocated:'", 'u.cost_id']) }} as order_id,
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    cast('unallocated_cost' as {{ dbt.type_string() }}) as row_type,
    u.cost_date as order_date,
    u.channel_id,
    ch.platform,
    cast(null as {{ dbt.type_string() }}) as status,
    {{ dx_bool(false) }} as is_provisional,
    cast(null as {{ dbt.type_string() }}) as customer_id,
    cast(0 as numeric) as gross_amount_vnd,
    cast(0 as numeric) as net_revenue_vnd,
    u.platform_fee_vnd,
    u.payment_fee_vnd,
    u.shipping_cost_vnd,
    u.allocated_ad_spend_vnd,
    u.other_cost_vnd,
    cast(0 as numeric) as return_cost_vnd,
    cast(0 as numeric) as cogs_vnd,
    {{ dx_bool(false) }} as has_missing_cogs,
    {{ dx_bool(false) }} as is_cancelled,
    {{ dx_bool(false) }} as is_returned
from unalloc as u
left join ch on ch.channel_id = u.channel_id
