{#- Người mua sau khi ghép; chỉ có dạng băm (NFR-03). GĐ1: theo `buyer_ref`, nếu không thì `phone_hash`. -#}
with o as (
    select * from {{ ref('int_orders') }} where customer_id is not null
),

r as (
    select o.*, row_number() over (partition by customer_id order by ordered_at, source_id) as rn
    from o
),

agg as (
    select
        customer_id,
        max(buyer_phone_hash) as phone_hash,
        max(buyer_email_hash) as email_hash,
        min(ordered_at) as first_order_at,
        count(*) as order_count_lifetime
    from o
    group by customer_id
)

select
    a.customer_id,
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    r.source,
    r.source_id,
    a.phone_hash,
    a.email_hash,
    a.first_order_at,
    r.channel_id as first_channel_id,
    a.order_count_lifetime
from agg as a
inner join r on r.customer_id = a.customer_id and r.rn = 1
