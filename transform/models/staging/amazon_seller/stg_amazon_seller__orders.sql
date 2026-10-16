{{ config(enabled='amazon_seller' in var('sources', [])) }}
{#- Đơn Amazon Seller Central qua Windsor, tiền USD (FR-MOD-03). -#}
with o as (
    select * from (
        select *, row_number() over (partition by amazon_order_id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'amazon_seller__orders') }}
    ) as src where rn = 1
),

items as (
    select
        amazon_order_id,
        sum({{ dx_num('item_price_amount') }}) as gross_o,
        sum(coalesce({{ dx_num('promotion_discount_amount') }}, 0)) as promo_o
    from (
        select *, row_number() over (partition by amazon_order_id, order_item_id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'amazon_seller__order_items') }}
    ) as x
    where rn = 1
    group by amazon_order_id
),

fe as (
    select amazon_order_id, min(posted_date) as posted
    from {{ source('raw', 'amazon_seller__financial_events') }}
    where event_type = 'ShipmentEvent'
    group by amazon_order_id
),

a as (
    select
        o.*,
        {{ dx_ts('o.purchase_date') }} as ordered_at_utc,
        {{ dx_ts('o.last_update_date') }} as updated_at_utc,
        {{ dx_ts('fe.posted') }} as settled_at_utc,
        coalesce(items.gross_o, {{ dx_num('o.order_total_amount') }}) as gross_o,
        coalesce(items.promo_o, 0) as seller_disc_o,
        {{ dx_str('o.order_total_currency') }} as cur
    from o
    left join items on items.amazon_order_id = o.amazon_order_id
    left join fe on fe.amazon_order_id = o.amazon_order_id
),

b as (select a.*, {{ dx_vn_date('ordered_at_utc') }} as order_date from a)

select
    cast('amazon_seller' as {{ dbt.type_string() }}) as source,
    {{ dx_str('b.amazon_order_id') }} as source_id,
    {{ dx_str('b._dx_source_account') }} as source_account,
    b.ordered_at_utc as ordered_at,
    b.updated_at_utc as updated_at,
    b.order_date,
    {{ dx_str('b.order_status') }} as status_raw,
    {{ dx_status_value() }} as status,
    cast(null as {{ dbt.type_string() }}) as buyer_ref,
    cast(null as {{ dbt.type_string() }}) as buyer_phone_hash,
    {{ pii_hash('b.buyer_email', 'email') }} as buyer_email_hash,
    b.cur as currency,
    cast(b.gross_o as numeric) as gross_amount_original,
    cast(b.seller_disc_o as numeric) as discount_amount_original,
    cast(b.seller_disc_o as numeric) as seller_discount_original,
    cast(0 as numeric) as platform_discount_original,
    {{ to_vnd('b.gross_o', 'b.cur', 'b.order_date') }} as gross_amount_vnd,
    {{ to_vnd('b.seller_disc_o', 'b.cur', 'b.order_date') }} as discount_amount_vnd,
    {{ to_vnd('b.gross_o - b.seller_disc_o', 'b.cur', 'b.order_date') }} as net_amount_vnd,
    b.settled_at_utc as settled_at
from b
{{ dx_status_joins('amazon_seller', 'b.order_status') }}
{{ dx_fx_join('b.cur', 'b.order_date') }}
