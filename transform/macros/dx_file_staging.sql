{#- Staging chung cho dữ liệu từ file của lượt kiểm tra sức khỏe (spec 07 §4.2). Adapter đã chuẩn hóa file về
các bảng `<src>__orders`, `__order_lines`, `__fees`, `__ad_insights_daily` (và đã bỏ thông tin người mua), nên
staging chỉ tính tiền, ánh xạ trạng thái/phí bằng seed của sàn tương ứng và quy đổi VND theo hợp đồng spec 02 §3.2.
-#}

{% macro dx_file_orders(src, platform) -%}
with o as (
    select * from {{ source('raw', src ~ '__orders') }}
),

l as (
    select
        order_id,
        sum({{ dx_num('unit_original_price') }} * quantity) as gross_o,
        sum(coalesce({{ dx_num('line_seller_discount') }}, 0)) as line_seller_o,
        sum(coalesce({{ dx_num('line_platform_discount') }}, 0)) as line_platform_o
    from {{ source('raw', src ~ '__order_lines') }}
    group by order_id
),

f as (
    select order_id, min(fee_date) as settled_date
    from {{ source('raw', src ~ '__fees') }}
    group by order_id
),

a as (
    select
        o.*,
        cast(o.ordered_at as timestamp) as ordered_at_utc,
        {{ dx_vn_date('cast(o.ordered_at as timestamp)') }} as order_date,
        coalesce(l.gross_o, 0) as gross_o,
        coalesce(l.line_seller_o, 0) + coalesce({{ dx_num('o.order_seller_discount') }}, 0) as seller_disc_o,
        coalesce(l.line_platform_o, 0) + coalesce({{ dx_num('o.order_platform_discount') }}, 0) as platform_disc_o,
        f.settled_date
    from o
    left join l on l.order_id = o.order_id
    left join f on f.order_id = o.order_id
)

select
    cast('{{ src }}' as {{ dbt.type_string() }}) as source,
    {{ dx_str('a.order_id') }} as source_id,
    cast('file' as {{ dbt.type_string() }}) as source_account,
    a.ordered_at_utc as ordered_at,
    a.ordered_at_utc as updated_at,
    a.order_date,
    {{ dx_str('a.status_raw') }} as status_raw,
    {{ dx_status_value() }} as status,
    {{ dx_str('a.buyer_ref_hash') }} as buyer_ref,
    cast(null as {{ dbt.type_string() }}) as buyer_phone_hash,
    cast(null as {{ dbt.type_string() }}) as buyer_email_hash,
    {{ dx_str('a.currency') }} as currency,
    cast(a.gross_o as numeric) as gross_amount_original,
    cast(a.seller_disc_o + a.platform_disc_o as numeric) as discount_amount_original,
    cast(a.seller_disc_o as numeric) as seller_discount_original,
    cast(a.platform_disc_o as numeric) as platform_discount_original,
    {{ to_vnd('a.gross_o', 'a.currency', 'a.order_date') }} as gross_amount_vnd,
    {{ to_vnd('a.seller_disc_o + a.platform_disc_o', 'a.currency', 'a.order_date') }} as discount_amount_vnd,
    {{ to_vnd('a.gross_o - a.seller_disc_o', 'a.currency', 'a.order_date') }} as net_amount_vnd,
    case when a.settled_date is not null then cast(a.settled_date as timestamp) end as settled_at
from a
{{ dx_status_joins(platform, 'a.status_raw') }}
{{ dx_fx_join('a.currency', 'a.order_date') }}
{%- endmacro %}


{% macro dx_file_order_lines(src) -%}
with li as (
    select * from {{ source('raw', src ~ '__order_lines') }}
),

o as (
    select order_id, currency, ordered_at, coalesce({{ dx_num('order_seller_discount') }}, 0) as voucher
    from {{ source('raw', src ~ '__orders') }}
),

lines as (
    select
        li.*,
        o.currency,
        o.voucher,
        {{ dx_vn_date('cast(o.ordered_at as timestamp)') }} as order_date,
        {{ dx_num('li.unit_original_price') }} * li.quantity as gross_o,
        {{ dx_num('li.unit_original_price') }} * li.quantity - coalesce({{ dx_num('li.line_seller_discount') }}, 0)
            as net_o,
        sum({{ dx_num('li.unit_original_price') }} * li.quantity - coalesce({{ dx_num('li.line_seller_discount') }}, 0))
            over (partition by li.order_id) as order_net_total
    from li
    inner join o on o.order_id = li.order_id
),

priced as (
    select
        lines.*,
        coalesce({{ dx_num('line_seller_discount') }}, 0) + voucher * {{ dx_div('net_o', 'order_net_total') }}
            as alloc_disc_o
    from lines
)

select
    cast('{{ src }}' as {{ dbt.type_string() }}) as source,
    {{ dx_str('p.line_id') }} as source_id,
    {{ dx_str('p.order_id') }} as order_source_id,
    trim({{ dx_str('p.seller_sku') }}) as seller_sku,
    {{ dx_str('p.item_name') }} as item_name,
    cast(p.quantity as bigint) as quantity,
    {{ to_vnd(dx_div('p.net_o', 'p.quantity'), 'p.currency', 'p.order_date') }} as unit_price_vnd,
    {{ to_vnd('p.gross_o', 'p.currency', 'p.order_date') }} as line_gross_vnd,
    {{ to_vnd('coalesce(' ~ dx_num('p.alloc_disc_o') ~ ', 0)', 'p.currency', 'p.order_date') }} as allocated_discount_vnd
from priced as p
{{ dx_fx_join('p.currency', 'p.order_date') }}
{%- endmacro %}


{% macro dx_file_fees(src, platform) -%}
with f as (
    select * from {{ source('raw', src ~ '__fees') }}
)

select
    cast('{{ src }}' as {{ dbt.type_string() }}) as source,
    {{ dx_str('f.fee_id') }} as source_id,
    {{ dx_str('f.order_id') }} as order_source_id,
    cast('file' as {{ dbt.type_string() }}) as source_account,
    cast(f.fee_date as date) as fee_date,
    {{ dx_str('f.fee_type_raw') }} as fee_type_raw,
    cast(ft.cost_type as {{ dbt.type_string() }}) as cost_type,
    cast({{ dx_num('f.amount') }} as numeric) as amount_original,
    {{ dx_str('f.currency') }} as currency,
    {{ to_vnd(dx_num('f.amount'), dx_str('f.currency'), 'cast(f.fee_date as date)') }} as amount_vnd
from f
left join {{ ref('fee_type_map__' ~ platform) }} as ft on ft.fee_type_raw = {{ dx_str('f.fee_type_raw') }}
{{ dx_fx_join(dx_str('f.currency'), 'cast(f.fee_date as date)') }}
where f.fee_date is not null and coalesce(ft.cost_type, '') <> 'exclude'
{%- endmacro %}


{% macro dx_file_returns(src) -%}
with r as (
    select * from {{ source('raw', src ~ '__returns') }}
),

o as (
    select order_id, currency from {{ source('raw', src ~ '__orders') }}
),

b as (
    select r.*, cast(r.returned_at as timestamp) as returned_at_utc, coalesce(o.currency, 'VND') as currency
    from r left join o on o.order_id = r.order_id
)

{#- File xuất đơn không có lý do hoàn: ghi `other`. -#}
select
    cast('{{ src }}' as {{ dbt.type_string() }}) as source,
    {{ dx_str('b.return_id') }} as source_id,
    {{ dx_str('b.order_id') }} as order_source_id,
    {{ dx_str('b.line_id') }} as order_line_source_id,
    b.returned_at_utc as returned_at,
    {{ dx_vn_date('b.returned_at_utc') }} as return_date,
    cast(null as {{ dbt.type_string() }}) as reason_raw,
    cast('other' as {{ dbt.type_string() }}) as reason,
    {{ to_vnd(dx_num('b.refund_amount'), 'b.currency', dx_vn_date('b.returned_at_utc')) }} as refund_amount_vnd,
    {{ to_vnd('coalesce(' ~ dx_num('b.return_fee') ~ ', 0)', 'b.currency', dx_vn_date('b.returned_at_utc')) }} as return_fee_vnd,
    cast('completed' as {{ dbt.type_string() }}) as status
from b
{{ dx_fx_join('b.currency', dx_vn_date('b.returned_at_utc')) }}
{%- endmacro %}


{% macro dx_file_products(src) -%}
select
    cast('{{ src }}' as {{ dbt.type_string() }}) as source,
    trim({{ dx_str('seller_sku') }}) as source_id,
    trim({{ dx_str('seller_sku') }}) as seller_sku,
    max({{ dx_str('item_name') }}) as name,
    cast(null as {{ dbt.type_string() }}) as barcode,
    cast(null as {{ dbt.type_string() }}) as category_raw
from {{ source('raw', src ~ '__order_lines') }}
where seller_sku is not null and trim({{ dx_str('seller_sku') }}) <> ''
group by trim({{ dx_str('seller_sku') }})
{%- endmacro %}


{% macro dx_file_ads(src) -%}
with a as (
    select * from {{ source('raw', src ~ '__ad_insights_daily') }}
)

select
    cast('{{ src }}' as {{ dbt.type_string() }}) as source,
    cast('file' as {{ dbt.type_string() }}) as source_account,
    cast(a.date as date) as date,
    {{ dx_str('a.campaign_id') }} as campaign_id,
    {{ dx_str('a.campaign_name') }} as campaign_name,
    {{ dx_str('a.adgroup_id') }} as adgroup_id,
    {{ dx_str('a.adgroup_name') }} as adgroup_name,
    {{ dx_str('a.currency') }} as currency,
    {{ dx_num('a.spend') }} as spend_original,
    {{ to_vnd(dx_num('a.spend'), dx_str('a.currency'), 'cast(a.date as date)') }} as spend_vnd,
    cast(a.impressions as bigint) as impressions,
    cast(a.clicks as bigint) as clicks,
    {{ dx_num('a.conversions') }} as conversions,
    {{ dx_num('a.conversion_value') }} as conversion_value_original,
    {{ to_vnd(dx_num('a.conversion_value'), dx_str('a.currency'), 'cast(a.date as date)') }} as conversion_value_vnd
from a
{{ dx_fx_join(dx_str('a.currency'), 'cast(a.date as date)') }}
{%- endmacro %}
