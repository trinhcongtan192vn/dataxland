{#- Một khoản chi gắn với đơn, kênh hoặc ngày. Chi quảng cáo sinh từ `fct_ad_performance_daily` theo kênh và ngày
(architecture §5.3, spec 02 §4). -#}
with fees as (
    select
        {{ dbt_utils.generate_surrogate_key(['f.source', 'f.source_id']) }} as cost_id,
        f.source,
        f.source_id,
        f.cost_type,
        f.amount_vnd,
        case when f.order_source_id is not null then {{ dbt_utils.generate_surrogate_key(['f.source', 'f.order_source_id']) }} end as order_id,
        {{ dbt_utils.generate_surrogate_key(['f.source', 'f.source_account']) }} as channel_id,
        f.fee_date as cost_date
    from {{ ref('int_union__fees') }} as f
),

ad as (
    select channel_id, date, min(source) as source, sum(spend_vnd) as amount_vnd
    from {{ ref('fct_ad_performance_daily') }}
    group by channel_id, date
)

select cost_id, {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at, source, source_id, cost_type, cast(amount_vnd as numeric) as amount_vnd,
    order_id, channel_id, cost_date
from fees
union all
select
    {{ dbt_utils.generate_surrogate_key(['ad.channel_id', dx_str('ad.date'), "'ad_spend'"]) }} as cost_id,
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    ad.source,
    {{ dbt.concat(['ad.channel_id', "'|'", dx_str('ad.date')]) }} as source_id,
    cast('ad_spend' as {{ dbt.type_string() }}) as cost_type,
    cast(ad.amount_vnd as numeric) as amount_vnd,
    cast(null as {{ dbt.type_string() }}) as order_id,
    ad.channel_id,
    ad.date as cost_date
from ad
where ad.amount_vnd <> 0
