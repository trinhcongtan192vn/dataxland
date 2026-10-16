{#- Một đơn trên một kênh (spec 02 §4, §4.1). -#}
{%- set win = var('provisional_window_days', {'default': 14}) %}
{%- set win_default = (win['default'] if (win is mapping and 'default' in win) else 14) | int %}
with o as (
    select * from {{ ref('int_orders') }}
),

l as (
    select
        order_id,
        sum(cogs_vnd) as cogs_known_vnd,
        max(case when has_missing_cogs then 1 else 0 end) as missing
    from {{ ref('int_order_lines') }}
    group by order_id
),

f as (
    select
        o.*,
        {%- if win.keys() | reject('equalto', 'default') | list | length > 0 %}
        case
            {%- for s, d in win.items() if s != 'default' %}
            when o.source = '{{ s }}' then {{ d | int }}
            {%- endfor %}
            else {{ win_default }}
        end as prov_days,
        {%- else %}
        {{ win_default }} as prov_days,
        {%- endif %}
        l.cogs_known_vnd,
        coalesce(l.missing, 0) as missing
    from o
    left join l on l.order_id = o.order_id
)

select
    f.order_id,
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    f.source,
    f.source_id,
    f.channel_id,
    f.customer_id,
    f.ordered_at,
    f.order_date,
    f.status,
    f.status_raw,
    f.currency,
    f.gross_amount_original,
    f.gross_amount_vnd,
    f.discount_amount_vnd,
    f.net_amount_vnd,
    f.settled_at,
    (f.settled_at is not null) as is_settled,
    (f.settled_at is null and {{ dbt.datediff('f.order_date', dx_today(), 'day') }} < f.prov_days) as is_provisional,
    (f.status in ('completed', 'cancelled', 'returned', 'failed_delivery')) as is_final_status,
    (f.status = 'cancelled') as is_cancelled,
    cast(case when f.missing = 1 then null else coalesce(f.cogs_known_vnd, 0) end as numeric) as cogs_vnd,
    cast(coalesce(f.cogs_known_vnd, 0) as numeric) as cogs_known_vnd,
    (f.missing = 1) as has_missing_cogs
from f
