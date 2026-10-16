{{ config(enabled='tiktok_shop' in var('sources', [])) }}
{#- Đơn TikTok Shop (spec 01 §4). -#}
with o as (
    select * from (
        select *, row_number() over (partition by id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'tiktok_shop__orders') }}
    ) as src where rn = 1
),

st as (
    select order_id, min(statement_time) as statement_time
    from {{ source('raw', 'tiktok_shop__settlements') }}
    group by order_id
),

a as (
    select
        o.*,
        {{ dx_from_unix('o.create_time') }} as ordered_at_utc,
        {{ dx_from_unix('o.update_time') }} as updated_at_utc,
        case when st.statement_time is not null then {{ dx_from_unix('st.statement_time') }} end as settled_at_utc,
        {{ dx_num('o.original_total_product_price') }} as gross_o,
        coalesce({{ dx_num('o.seller_discount') }}, 0) as seller_disc_o,
        coalesce({{ dx_num('o.platform_discount') }}, 0) as platform_disc_o
    from o
    left join st on st.order_id = o.id
),

b as (select a.*, {{ dx_vn_date('ordered_at_utc') }} as order_date from a)

select
    cast('tiktok_shop' as {{ dbt.type_string() }}) as source,
    {{ dx_str('b.id') }} as source_id,
    {{ dx_str('b._dx_source_account') }} as source_account,
    b.ordered_at_utc as ordered_at,
    b.updated_at_utc as updated_at,
    b.order_date,
    {{ dx_str('b.status') }} as status_raw,
    {{ dx_status_value() }} as status,
    {{ dx_str('b.user_id') }} as buyer_ref,
    {{ pii_hash('b.recipient_phone_number', 'phone') }} as buyer_phone_hash,
    {{ pii_hash('b.buyer_email', 'email') }} as buyer_email_hash,
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
{{ dx_status_joins('tiktok_shop', 'b.status') }}
{{ dx_fx_join('b.currency', 'b.order_date') }}
