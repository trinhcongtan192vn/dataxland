{{ config(enabled=var('pack') in ['agency']) }}
{#- Tháng × nền tảng: ngân sách, đã chi trong tháng đến hôm qua, số ngày (spec 02 §5, spec 03 §3.3 `budget_pacing`). -#}
{%- set yesterday = dbt.dateadd('day', -1, dx_today()) %}
with b as (
    select platform, month, sum(budget_vnd) as budget_vnd
    from {{ ref('dim_ad_budget') }}
    group by platform, month
),

s as (
    select
        cast({{ dbt.date_trunc('month', 'a.date') }} as date) as month,
        ch.platform,
        sum(a.spend_vnd) as spend_vnd
    from {{ ref('fct_ad_performance_daily') }} as a
    inner join {{ ref('dim_channel') }} as ch on ch.channel_id = a.channel_id
    where a.date <= cast({{ yesterday }} as date)
    group by 1, 2
),

m as (
    select
        coalesce(b.month, s.month) as month,
        coalesce(b.platform, s.platform) as platform,
        cast(coalesce(b.budget_vnd, 0) as numeric) as budget_vnd,
        cast(coalesce(s.spend_vnd, 0) as numeric) as spend_mtd_vnd
    from b
    full outer join s on s.month = b.month and s.platform = b.platform
),

d as (
select
    m.*,
    {{ dbt.datediff('m.month', dbt.dateadd('month', 1, 'm.month'), 'day') }} as days_in_month,
    case
        when cast({{ yesterday }} as date) >= {{ dx_month_end('m.month') }}
            then {{ dbt.datediff('m.month', dbt.dateadd('month', 1, 'm.month'), 'day') }}
        when cast({{ yesterday }} as date) < m.month then 0
        else {{ dbt.datediff('m.month', 'cast(' ~ yesterday ~ ' as date)', 'day') }} + 1
    end as days_elapsed
from m
)

select
    {{ dbt_utils.generate_surrogate_key(['d.platform', dx_str('d.month')]) }} as budget_monthly_id,
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    d.month,
    d.platform,
    d.budget_vnd,
    d.spend_mtd_vnd,
    d.days_in_month,
    d.days_elapsed,
    {#- Mức chi đúng tiến độ, cộng được qua nhiều nền tảng (dùng cho `budget_pacing`, spec 03 §3.3). -#}
    cast(d.budget_vnd * cast(d.days_elapsed as {{ dx_type_float() }}) / cast(d.days_in_month as {{ dx_type_float() }}) as numeric) as budget_expected_mtd_vnd
from d
