{{ config(enabled='amazon_seller' in var('sources', [])) }}
{#- Phí Amazon từ financial events: số âm là tiền người bán trả (spec 01 §8.1). -#}
with f as (
    select * from (
        select *, row_number() over (partition by event_id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'amazon_seller__financial_events') }}
    ) as src where rn = 1
)

select
    cast('amazon_seller' as {{ dbt.type_string() }}) as source,
    {{ dx_str('f.event_id') }} as source_id,
    {{ dx_str('f.amazon_order_id') }} as order_source_id,
    {{ dx_str('f._dx_source_account') }} as source_account,
    {{ dx_vn_date(dx_ts('f.posted_date')) }} as fee_date,
    {{ dx_str('f.fee_type') }} as fee_type_raw,
    cast(ft.cost_type as {{ dbt.type_string() }}) as cost_type,
    cast(-1 * {{ dx_num('f.amount') }} as numeric) as amount_original,
    {{ dx_str('f.currency') }} as currency,
    {{ to_vnd('-1 * ' ~ dx_num('f.amount'), dx_str('f.currency'), dx_vn_date(dx_ts('f.posted_date'))) }} as amount_vnd
from f
left join {{ ref('fee_type_map__amazon_seller') }} as ft on ft.fee_type_raw = {{ dx_str('f.fee_type') }}
{{ dx_fx_join(dx_str('f.currency'), dx_vn_date(dx_ts('f.posted_date'))) }}
where f.event_type = 'ShipmentEvent' and coalesce(ft.cost_type, '') <> 'exclude'
