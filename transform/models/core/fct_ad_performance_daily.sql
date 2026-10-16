{#- Một nhóm quảng cáo trong một ngày, số chuyển đổi và giá trị do nền tảng báo (architecture §5.3). -#}
select
    {{ dbt_utils.generate_surrogate_key(['a.source', 'a.source_account', 'a.campaign_id', 'a.adgroup_id', 'a.date']) }} as ad_performance_id,
    {{ dbt_utils.generate_surrogate_key(['a.source', 'a.source_account']) }} as channel_id,
    a.campaign_id,
    a.adgroup_id,
    a.date,
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    a.source,
    {{ dbt.concat(['a.source_account', "'|'", 'a.campaign_id', "'|'", 'a.adgroup_id', "'|'", dx_str('a.date')]) }} as source_id,
    a.campaign_name,
    a.adgroup_name,
    a.currency,
    a.spend_original,
    a.spend_vnd as spend,
    a.spend_vnd,
    a.impressions,
    a.clicks,
    a.conversions,
    a.conversion_value_vnd as conversion_value,
    a.conversion_value_vnd
from {{ ref('int_union__ad_insights_daily') }} as a
