{{ config(enabled='lazada' in var('sources', [])) }}
{#- Đơn Lazada (spec 01 §5). Thời điểm dạng `YYYY-MM-DD HH:MM:SS +0700`. -#}
with o as (
    select * from (
        select *, row_number() over (partition by order_id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'lazada__orders') }}
    ) as src where rn = 1
),

tx as (
    select order_no, min(cast(transaction_date as date)) as settle_date
    from {{ source('raw', 'lazada__transactions') }}
    group by order_no
),

a as (
    select
        o.*,
        {{ dx_from_local_vn(dx_str('o.created_at')) }} as ordered_at_utc,
        {{ dx_from_local_vn(dx_str('o.updated_at')) }} as updated_at_utc,
        case when tx.settle_date is not null then {{ dbt.dateadd('hour', -7, dx_ts('tx.settle_date')) }} end as settled_at_utc,
        {{ dx_num('o.price') }} as gross_o,
        coalesce({{ dx_num('o.voucher_seller') }}, 0) as seller_disc_o,
        coalesce({{ dx_num('o.voucher_platform') }}, 0) as platform_disc_o
    from o
    left join tx on {{ dx_str('tx.order_no') }} = {{ dx_str('o.order_id') }}
),

b as (select a.*, {{ dx_vn_date('ordered_at_utc') }} as order_date from a)

select
    cast('lazada' as {{ dbt.type_string() }}) as source,
    {{ dx_str('b.order_id') }} as source_id,
    {{ dx_str('b._dx_source_account') }} as source_account,
    b.ordered_at_utc as ordered_at,
    b.updated_at_utc as updated_at,
    b.order_date,
    {{ dx_str('b.statuses') }} as status_raw,
    {{ dx_status_value() }} as status,
    cast(null as {{ dbt.type_string() }}) as buyer_ref,
    {{ pii_hash('b.address_phone', 'phone') }} as buyer_phone_hash,
    cast(null as {{ dbt.type_string() }}) as buyer_email_hash,
    {{ dx_str('b.currency') }} as currency,
    cast(b.gross_o as numeric) as gross_amount_original,
    cast(b.seller_disc_o + b.platform_disc_o as numeric) as discount_amount_original,
    cast(b.seller_disc_o as numeric) as seller_discount_original,
    cast(b.platform_disc_o as numeric) as platform_discount_original,
    {{ to_vnd('b.gross_o', 'b.currency', 'b.order_date') }} as gross_amount_vnd,
    {{ to_vnd('b.seller_disc_o + b.platform_disc_o', 'b.currency', 'b.order_date') }} as discount_amount_vnd,
    {{ to_vnd('b.gross_o - b.seller_disc_o', 'b.currency', 'b.order_date') }} as net_amount_vnd,
    b.settled_at_utc as settled_at
from b
{{ dx_status_joins('lazada', 'b.statuses') }}
{{ dx_fx_join('b.currency', 'b.order_date') }}
