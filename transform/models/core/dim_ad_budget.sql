{#- Ngân sách quảng cáo theo nền tảng và tháng, hoặc theo chiến dịch (FR-INP-05, spec 05 §6.5). Ngân sách cả nền
tảng: khách có nhiều tài khoản trên nền tảng thì chia đều cho các `channel_id` của nền tảng đó (spec 02 §4). Ngân
sách chiến dịch: gán cho tài khoản chạy chiến dịch đó; chưa thấy chiến dịch trong dữ liệu quảng cáo thì để
`channel_id` "chưa gán" của nền tảng. -#}
with b as (
    {% if 'portal' in var('sources', []) -%}
    select source_id, platform, month, campaign_id, budget_vnd
    from {{ ref('stg_portal__ad_budgets') }}
    where not deleted
    {%- else -%}
    select cast(null as {{ dbt.type_string() }}) as source_id, cast(null as {{ dbt.type_string() }}) as platform,
        cast(null as date) as month, cast(null as {{ dbt.type_string() }}) as campaign_id,
        cast(null as numeric) as budget_vnd where 1 = 0
    {%- endif %}
),

ch as (
    select channel_id, platform, count(*) over (partition by platform) as n
    from {{ ref('dim_channel') }}
    where channel_type = 'ads'
),

cc as (
    select c.platform, f.campaign_id, min(f.channel_id) as channel_id
    from {{ ref('fct_ad_performance_daily') }} as f
    inner join {{ ref('dim_channel') }} as c on c.channel_id = f.channel_id
    group by c.platform, f.campaign_id
)

select
    case
        when b.campaign_id is null
            then coalesce(ch.channel_id, {{ dbt_utils.generate_surrogate_key(['b.platform', "'unassigned'"]) }})
        else coalesce(cc.channel_id, {{ dbt_utils.generate_surrogate_key(['b.platform', "'unassigned'"]) }})
    end as channel_id,
    b.month,
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    cast('portal' as {{ dbt.type_string() }}) as source,
    b.source_id,
    b.platform,
    b.campaign_id,
    cast(
        case when b.campaign_id is null then b.budget_vnd / coalesce(ch.n, 1) else b.budget_vnd end as numeric
    ) as budget_vnd
from b
left join ch on ch.platform = b.platform and b.campaign_id is null
left join cc on cc.platform = b.platform and cc.campaign_id = b.campaign_id
