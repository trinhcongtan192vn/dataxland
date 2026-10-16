{{ config(enabled='shopee' in var('sources', [])) }}
{#- Phí Shopee từ quyết toán (escrow). Phí vận chuyển người bán chịu = phí thực tế − trợ giá − người mua trả.
Phí trả hàng lấy từ bảng hoàn hàng, không lấy ở đây để không tính trùng. -#}
with e as (
    select * from (
        select *, row_number() over (partition by order_sn order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'shopee__escrow') }}
    ) as src where rn = 1
),

o as (
    select order_sn, currency, _dx_source_account from (
        select *, row_number() over (partition by order_sn order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'shopee__orders') }}
    ) as x where rn = 1
),

unpivoted as (
    {% for fee, expr in [
        ('commission_fee', 'e.commission_fee'),
        ('service_fee', 'e.service_fee'),
        ('seller_transaction_fee', 'e.seller_transaction_fee'),
        ('net_shipping_fee', 'e.actual_shipping_fee - e.shopee_shipping_rebate - e.buyer_paid_shipping_fee'),
    ] %}
    select
        e.order_sn,
        e._dx_source_account,
        {{ dx_vn_date(dx_from_unix('e.escrow_release_time')) }} as fee_date,
        '{{ fee }}' as fee_type_raw,
        {{ dx_num(expr) }} as amount_o
    from e
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

select
    cast('shopee' as {{ dbt.type_string() }}) as source,
    {{ dbt.concat([dx_str('u.order_sn'), "'-'", 'u.fee_type_raw']) }} as source_id,
    {{ dx_str('u.order_sn') }} as order_source_id,
    {{ dx_str('u._dx_source_account') }} as source_account,
    u.fee_date,
    cast(u.fee_type_raw as {{ dbt.type_string() }}) as fee_type_raw,
    cast(ft.cost_type as {{ dbt.type_string() }}) as cost_type,
    cast(u.amount_o as numeric) as amount_original,
    {{ dx_str("coalesce(o.currency, 'VND')") }} as currency,
    {{ to_vnd('u.amount_o', "coalesce(o.currency, 'VND')", 'u.fee_date') }} as amount_vnd
from unpivoted as u
left join o on o.order_sn = u.order_sn
left join {{ ref('fee_type_map__shopee') }} as ft on ft.fee_type_raw = u.fee_type_raw
{{ dx_fx_join("coalesce(o.currency, 'VND')", 'u.fee_date') }}
where u.amount_o <> 0 and coalesce(ft.cost_type, '') <> 'exclude'
