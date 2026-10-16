{{ config(enabled='amazon_seller' in var('sources', [])) }}
{#- Hoàn tiền Amazon từ RefundEvent (cả đơn). -#}
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
    cast(null as {{ dbt.type_string() }}) as order_line_source_id,
    {{ dx_ts('f.posted_date') }} as returned_at,
    {{ dx_vn_date(dx_ts('f.posted_date')) }} as return_date,
    {{ dx_str('f.fee_type') }} as reason_raw,
    cast(rr.reason as {{ dbt.type_string() }}) as reason,
    {{ to_vnd('-1 * ' ~ dx_num('f.amount'), dx_str('f.currency'), dx_vn_date(dx_ts('f.posted_date'))) }} as refund_amount_vnd,
    cast(0 as numeric) as return_fee_vnd,
    cast('refunded' as {{ dbt.type_string() }}) as status
from f
left join {{ ref('return_reason_map__amazon_seller') }} as rr on rr.reason_raw = {{ dx_str('f.fee_type') }}
{{ dx_fx_join(dx_str('f.currency'), dx_vn_date(dx_ts('f.posted_date'))) }}
where f.event_type = 'RefundEvent'
