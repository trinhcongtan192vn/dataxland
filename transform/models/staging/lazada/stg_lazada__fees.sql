{{ config(enabled='lazada' in var('sources', [])) }}
{#- Phí Lazada từ giao dịch tài chính; số âm là tiền người bán trả, đổi thành số dương (spec 02 §3.2). -#}
with t as (
    select * from (
        select *, row_number() over (partition by transaction_id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'lazada__transactions') }}
    ) as src where rn = 1
),

o as (
    select order_id, currency from (
        select *, row_number() over (partition by order_id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'lazada__orders') }}
    ) as x where rn = 1
)

select
    cast('lazada' as {{ dbt.type_string() }}) as source,
    {{ dx_str('t.transaction_id') }} as source_id,
    {{ dx_str('t.order_no') }} as order_source_id,
    {{ dx_str('t._dx_source_account') }} as source_account,
    cast(t.transaction_date as date) as fee_date,
    {{ dx_str('t.fee_name') }} as fee_type_raw,
    cast(ft.cost_type as {{ dbt.type_string() }}) as cost_type,
    cast(-1 * {{ dx_num('t.amount') }} as numeric) as amount_original,
    {{ dx_str("coalesce(o.currency, 'VND')") }} as currency,
    {{ to_vnd('-1 * ' ~ dx_num('t.amount'), "coalesce(o.currency, 'VND')", 'cast(t.transaction_date as date)') }} as amount_vnd
from t
left join o on {{ dx_str('o.order_id') }} = {{ dx_str('t.order_no') }}
left join {{ ref('fee_type_map__lazada') }} as ft on ft.fee_type_raw = {{ dx_str('t.fee_name') }}
{{ dx_fx_join("coalesce(o.currency, 'VND')", 'cast(t.transaction_date as date)') }}
where coalesce(ft.cost_type, '') <> 'exclude'
