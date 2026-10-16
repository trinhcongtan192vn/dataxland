{{ config(severity='warn', tags=['cogs']) }}
{#- Cảnh báo SKU có doanh thu 30 ngày mà chưa có giá vốn (FR-INP-03, spec 02 §6.1). Không chặn. -#}
select
    lower(trim(l.seller_sku)) as sku,
    sum(l.line_net_vnd) as revenue_30d
from {{ ref('fct_order_line') }} as l
inner join {{ ref('fct_order') }} as o on o.order_id = l.order_id
where l.has_missing_cogs
    and not o.is_cancelled
    and l.order_date >= cast({{ dbt.dateadd('day', -30, dx_today()) }} as date)
group by 1
