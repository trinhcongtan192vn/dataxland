{#- Doanh thu thực nhận của đơn: `net_amount_vnd` trừ tiền hoàn; đơn hủy hoặc giao thất bại là 0 (spec 02 §5). -#}
{{ config(materialized='table') }}

with r as (
    select
        order_id,
        sum(refund_amount_vnd) as refund_vnd,
        sum(return_fee_vnd) as return_fee_vnd,
        count(*) as return_count
    from {{ ref('fct_return') }}
    group by order_id
)

select
    o.order_id,
    cast(case
        when o.status in ('cancelled', 'failed_delivery') then 0
        else o.net_amount_vnd - coalesce(r.refund_vnd, 0)
    end as numeric) as net_revenue_vnd,
    cast(coalesce(r.refund_vnd, 0) as numeric) as refund_vnd,
    cast(coalesce(r.return_fee_vnd, 0) as numeric) as return_fee_vnd,
    (o.status = 'returned' or coalesce(r.return_count, 0) > 0) as is_returned
from {{ ref('fct_order') }} as o
left join r on r.order_id = o.order_id
