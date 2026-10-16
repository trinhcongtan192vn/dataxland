{{ config(enabled='tiktok_ads' in var('sources', [])) }}
{#- Hiệu quả quảng cáo theo ngày × chiến dịch × nhóm quảng cáo (spec 01 §8.1). -#}
with a as (
    select * from (
        select *, row_number() over (partition by date, account_id, campaign_id, adgroup_id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'tiktok_ads__ad_insights_daily') }}
    ) as src where rn = 1
)

select
    cast('tiktok_ads' as {{ dbt.type_string() }}) as source,
    {{ dx_str('a.account_id') }} as source_account,
    cast(a.date as date) as date,
    {{ dx_str('a.campaign_id') }} as campaign_id,
    {{ dx_str('a.campaign_name') }} as campaign_name,
    {{ dx_str('a.adgroup_id') }} as adgroup_id,
    {{ dx_str('a.adgroup_name') }} as adgroup_name,
    {{ dx_str('a.currency') }} as currency,
    {{ dx_num('a.spend') }} as spend_original,
    {{ to_vnd(dx_num('a.spend'), dx_str('a.currency'), 'cast(a.date as date)') }} as spend_vnd,
    cast(a.impressions as bigint) as impressions,
    cast(a.clicks as bigint) as clicks,
    {{ dx_num('a.conversions') }} as conversions,
    {{ dx_num('a.conversion_value') }} as conversion_value_original,
    {{ to_vnd(dx_num('a.conversion_value'), dx_str('a.currency'), 'cast(a.date as date)') }} as conversion_value_vnd
from a
{{ dx_fx_join(dx_str('a.currency'), 'cast(a.date as date)') }}
