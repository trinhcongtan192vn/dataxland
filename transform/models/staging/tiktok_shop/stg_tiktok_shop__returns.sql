{{ config(enabled='tiktok_shop' in var('sources', [])) }}
with r as (
    select * from (
        select *, row_number() over (partition by return_id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'tiktok_shop__returns') }}
    ) as src where rn = 1
),

o as (
    select id, currency from (
        select *, row_number() over (partition by id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'tiktok_shop__orders') }}
    ) as x where rn = 1
),

b as (
    select r.*, {{ dx_from_unix('r.create_time') }} as returned_at_utc, coalesce(o.currency, 'VND') as currency
    from r left join o on o.id = r.order_id
)

select
    cast('tiktok_shop' as {{ dbt.type_string() }}) as source,
    {{ dx_str('b.return_id') }} as source_id,
    {{ dx_str('b.order_id') }} as order_source_id,
    {{ dx_str('b.line_item_id') }} as order_line_source_id,
    b.returned_at_utc as returned_at,
    {{ dx_vn_date('b.returned_at_utc') }} as return_date,
    {{ dx_str('b.return_reason') }} as reason_raw,
    cast(rr.reason as {{ dbt.type_string() }}) as reason,
    {{ to_vnd('b.refund_total', 'b.currency', dx_vn_date('b.returned_at_utc')) }} as refund_amount_vnd,
    {{ to_vnd('coalesce(' ~ dx_num('b.return_shipping_fee') ~ ', 0)', 'b.currency', dx_vn_date('b.returned_at_utc')) }} as return_fee_vnd,
    {{ dx_str('b.return_status') }} as status
from b
left join {{ ref('return_reason_map__tiktok_shop') }} as rr on rr.reason_raw = b.return_reason
{{ dx_fx_join('b.currency', dx_vn_date('b.returned_at_utc')) }}
