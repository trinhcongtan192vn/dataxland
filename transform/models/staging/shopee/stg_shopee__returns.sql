{{ config(enabled='shopee' in var('sources', [])) }}
{#- Hoàn hàng Shopee (spec 01 §3). Lý do chuẩn hóa qua seed. -#}
with r as (
    select * from (
        select *, row_number() over (partition by return_sn order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'shopee__returns') }}
    ) as src where rn = 1
),

o as (
    select order_sn, currency from (
        select *, row_number() over (partition by order_sn order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'shopee__orders') }}
    ) as x where rn = 1
),

base as (
    select r.*, {{ dx_from_unix('r.create_time') }} as returned_at_utc, coalesce(o.currency, 'VND') as currency
    from r left join o on o.order_sn = r.order_sn
)

select
    cast('shopee' as {{ dbt.type_string() }}) as source,
    {{ dx_str('b.return_sn') }} as source_id,
    {{ dx_str('b.order_sn') }} as order_source_id,
    case when b.item_id is not null then
        {{ dbt.concat([dx_str('b.order_sn'), "'-'", dx_str('b.item_id'), "'-'", dx_str('b.model_id')]) }}
    end as order_line_source_id,
    b.returned_at_utc as returned_at,
    {{ dx_vn_date('b.returned_at_utc') }} as return_date,
    {{ dx_str('b.reason') }} as reason_raw,
    cast(rr.reason as {{ dbt.type_string() }}) as reason,
    {{ to_vnd('b.refund_amount', 'b.currency', dx_vn_date('b.returned_at_utc')) }} as refund_amount_vnd,
    {{ to_vnd('coalesce(' ~ dx_num('b.return_ship_fee') ~ ', 0)', 'b.currency', dx_vn_date('b.returned_at_utc')) }} as return_fee_vnd,
    {{ dx_str('b.status') }} as status
from base as b
left join {{ ref('return_reason_map__shopee') }} as rr on rr.reason_raw = b.reason
{{ dx_fx_join('b.currency', dx_vn_date('b.returned_at_utc')) }}
