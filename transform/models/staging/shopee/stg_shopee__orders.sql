{{ config(enabled='shopee' in var('sources', [])) }}
{#- Đơn Shopee (spec 01 §3, spec 02 §3.2). Thông tin người mua chỉ còn dạng băm. -#}
with o as (
    select * from (
        select *, row_number() over (partition by order_sn order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'shopee__orders') }}
    ) as src where rn = 1
),

esc as (
    select order_sn, min(escrow_release_time) as release_time
    from {{ source('raw', 'shopee__escrow') }}
    group by order_sn
),

base as (
    select
        o.*,
        {{ dx_from_unix('o.create_time') }} as ordered_at_utc,
        {{ dx_from_unix('o.update_time') }} as updated_at_utc,
        case when esc.release_time is not null then {{ dx_from_unix('esc.release_time') }} end as settled_at_utc
    from o
    left join esc on esc.order_sn = o.order_sn
),

amounts as (
    select
        base.*,
        {{ dx_vn_date('ordered_at_utc') }} as order_date,
        {{ dx_num('order_original_amount') }} as gross_o,
        {{ dx_num('order_original_amount') }} - {{ dx_num('order_discounted_amount') }}
            + coalesce({{ dx_num('seller_voucher') }}, 0) as seller_disc_o,
        coalesce({{ dx_num('shopee_voucher') }}, 0) as platform_disc_o
    from base
)

select
    cast('shopee' as {{ dbt.type_string() }}) as source,
    {{ dx_str('a.order_sn') }} as source_id,
    {{ dx_str('a._dx_source_account') }} as source_account,
    a.ordered_at_utc as ordered_at,
    a.updated_at_utc as updated_at,
    a.order_date,
    {{ dx_str('a.order_status') }} as status_raw,
    {{ dx_status_value() }} as status,
    {{ dx_str('a.buyer_user_id') }} as buyer_ref,
    {{ pii_hash('a.recipient_phone', 'phone') }} as buyer_phone_hash,
    cast(null as {{ dbt.type_string() }}) as buyer_email_hash,
    {{ dx_str('a.currency') }} as currency,
    cast(a.gross_o as numeric) as gross_amount_original,
    cast(a.seller_disc_o + a.platform_disc_o as numeric) as discount_amount_original,
    cast(a.seller_disc_o as numeric) as seller_discount_original,
    cast(a.platform_disc_o as numeric) as platform_discount_original,
    {{ to_vnd('a.gross_o', 'a.currency', 'a.order_date') }} as gross_amount_vnd,
    {{ to_vnd('a.seller_disc_o + a.platform_disc_o', 'a.currency', 'a.order_date') }} as discount_amount_vnd,
    {{ to_vnd('a.gross_o - a.seller_disc_o', 'a.currency', 'a.order_date') }} as net_amount_vnd,
    a.settled_at_utc as settled_at
from amounts as a
{{ dx_status_joins('shopee', 'a.order_status') }}
{{ dx_fx_join('a.currency', 'a.order_date') }}
