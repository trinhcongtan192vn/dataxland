{#- Một gian hàng hoặc một tài khoản quảng cáo (architecture §5.3). -#}
with accts as (
    select source, source_account, currency from {{ ref('int_union__orders') }}
    union all
    select source, source_account, currency from {{ ref('int_union__ad_insights_daily') }}
),

g as (
    select source, source_account, min(currency) as currency
    from accts
    group by source, source_account
)

select
    {{ dbt_utils.generate_surrogate_key(['g.source', 'g.source_account']) }} as channel_id,
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    g.source,
    g.source_account as source_id,
    g.source_account,
    coalesce(pm.platform, g.source) as platform,
    coalesce(pm.channel_type, 'other') as channel_type,
    {{ dbt.concat(["coalesce(pm.name_vi, g.source)", "' · '", "g.source_account"]) }} as name,
    g.currency
from g
left join {{ ref('platform_map') }} as pm on pm.source = g.source
