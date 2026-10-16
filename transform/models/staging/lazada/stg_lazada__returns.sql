{{ config(enabled='lazada' in var('sources', [])) }}
with r as (
    select * from (
        select *, row_number() over (partition by reverse_order_id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'lazada__returns') }}
    ) as src where rn = 1
),

o as (
    select order_id, currency from (
        select *, row_number() over (partition by order_id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'lazada__orders') }}
    ) as x where rn = 1
),

b as (
    select r.*, {{ dx_from_local_vn(dx_str('r.created_at')) }} as returned_at_utc, coalesce(o.currency, 'VND') as currency
    from r left join o on {{ dx_str('o.order_id') }} = {{ dx_str('r.order_id') }}
)

select
    cast('lazada' as {{ dbt.type_string() }}) as source,
    {{ dx_str('b.reverse_order_id') }} as source_id,
    {{ dx_str('b.order_id') }} as order_source_id,
    {{ dx_str('b.order_item_id') }} as order_line_source_id,
    b.returned_at_utc as returned_at,
    {{ dx_vn_date('b.returned_at_utc') }} as return_date,
    {{ dx_str('b.reason_text') }} as reason_raw,
    cast(rr.reason as {{ dbt.type_string() }}) as reason,
    {{ to_vnd('b.refund_amount', 'b.currency', dx_vn_date('b.returned_at_utc')) }} as refund_amount_vnd,
    cast(0 as numeric) as return_fee_vnd,
    {{ dx_str('b.status') }} as status
from b
left join {{ ref('return_reason_map__lazada') }} as rr on rr.reason_raw = {{ dx_str('b.reason_text') }}
{{ dx_fx_join('b.currency', dx_vn_date('b.returned_at_utc')) }}
