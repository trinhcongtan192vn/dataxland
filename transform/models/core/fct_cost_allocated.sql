{#- Phân bổ chi phí (FR-MOD-05, spec 02 §4.2). Một dòng cho mỗi cặp (khoản chi, đơn nhận phân bổ).

| `cost_allocation` | Khoản đã gắn đơn | Khoản chưa gắn đơn |
|---|---|---|
| `by_revenue` | Giữ nguyên | Chia cho đơn không hủy cùng ngày (cùng kênh nếu là kênh bán) theo `net_amount_vnd` |
| `by_order` | Giữ nguyên | Chia đều theo số đơn không hủy |
| `none` | Giữ nguyên | Một dòng `order_id = null` |

Chi quảng cáo chia cho mọi kênh bán cùng ngày. Ngày không có đơn để nhận: một dòng `order_id = null`.
-#}
{%- set mode = var('cost_allocation', 'by_revenue') %}
with c as (
    select c.*, ch.channel_type
    from {{ ref('fct_cost') }} as c
    left join {{ ref('dim_channel') }} as ch on ch.channel_id = c.channel_id
),

o as (
    select order_id, order_date, channel_id, net_amount_vnd
    from {{ ref('fct_order') }}
    where not is_cancelled
),

linked as (
    select cost_id, order_id, cost_type, cost_date, channel_id, amount_vnd as allocated_amount_vnd
    from c
    where order_id is not null
),

unlinked as (
    select * from c where order_id is null
),

{% if mode == 'none' %}
spread as (
    select cost_id, cast(null as {{ dbt.type_string() }}) as order_id, cost_type, cost_date, channel_id,
        amount_vnd as allocated_amount_vnd
    from unlinked
)
{% else %}
targets as (
    select
        u.cost_id,
        o.order_id,
        o.net_amount_vnd as w_rev,
        sum(o.net_amount_vnd) over (partition by u.cost_id) as tot_rev,
        count(*) over (partition by u.cost_id) as tot_cnt
    from unlinked as u
    inner join o
        on o.order_date = u.cost_date
        and (u.channel_type = 'ads' or o.channel_id = u.channel_id)
),

spread as (
    select
        u.cost_id,
        t.order_id,
        u.cost_type,
        u.cost_date,
        u.channel_id,
        case
            {% if mode == 'by_order' %}when 1 = 1 then u.amount_vnd / cast(t.tot_cnt as {{ dx_type_float() }}){% endif %}
            when coalesce(t.tot_rev, 0) = 0 then u.amount_vnd / cast(t.tot_cnt as {{ dx_type_float() }})
            else u.amount_vnd * (cast(t.w_rev as {{ dx_type_float() }}) / cast(t.tot_rev as {{ dx_type_float() }}))
        end as allocated_amount_vnd
    from unlinked as u
    inner join targets as t on t.cost_id = u.cost_id
    union all
    select u.cost_id, cast(null as {{ dbt.type_string() }}) as order_id, u.cost_type, u.cost_date, u.channel_id,
        u.amount_vnd as allocated_amount_vnd
    from unlinked as u
    where not exists (select 1 from targets as t where t.cost_id = u.cost_id)
)
{% endif %}

select
    {{ dbt_utils.generate_surrogate_key(['x.cost_id', "coalesce(x.order_id, 'none')"]) }} as allocation_id,
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    x.cost_id,
    x.order_id,
    x.cost_type,
    x.cost_date,
    x.channel_id,
    cast(x.allocated_amount_vnd as numeric) as allocated_amount_vnd
from (
    select * from linked
    union all
    select * from spread
) as x
