{#- Ngân sách quảng cáo theo nền tảng và tháng. Khách có nhiều tài khoản trên một nền tảng thì chia đều cho
các `channel_id` của nền tảng đó (spec 02 §4). -#}
with b as (
    {% if 'portal' in var('sources', []) -%}
    select source_id, platform, month, budget_vnd from {{ ref('stg_portal__ad_budgets') }} where not deleted
    {%- else -%}
    select cast(null as {{ dbt.type_string() }}) as source_id, cast(null as {{ dbt.type_string() }}) as platform,
        cast(null as date) as month, cast(null as numeric) as budget_vnd where 1 = 0
    {%- endif %}
),

ch as (
    select channel_id, platform, count(*) over (partition by platform) as n
    from {{ ref('dim_channel') }}
    where channel_type = 'ads'
)

select
    coalesce(ch.channel_id, {{ dbt_utils.generate_surrogate_key(['b.platform', "'unassigned'"]) }}) as channel_id,
    b.month,
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    cast('portal' as {{ dbt.type_string() }}) as source,
    b.source_id,
    b.platform,
    cast(b.budget_vnd / coalesce(ch.n, 1) as numeric) as budget_vnd
from b
left join ch on ch.platform = b.platform
