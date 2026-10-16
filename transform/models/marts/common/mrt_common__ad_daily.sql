{#- Ngày × kênh quảng cáo × chiến dịch × nhóm (spec 02 §5). -#}
select
    a.ad_performance_id,
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    a.date,
    a.channel_id,
    ch.platform,
    ch.source_account as account_id,
    a.campaign_id,
    a.campaign_name,
    a.adgroup_id,
    a.adgroup_name,
    a.spend_vnd,
    a.impressions,
    a.clicks,
    a.conversions,
    a.conversion_value_vnd
from {{ ref('fct_ad_performance_daily') }} as a
left join {{ ref('dim_channel') }} as ch on ch.channel_id = a.channel_id
