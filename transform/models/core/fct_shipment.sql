{#- Một vận đơn của hãng vận chuyển (FR-ING-09, spec 01 §9): phí vận chuyển, COD, phí hoàn theo vận đơn; gắn với đơn
của sàn khi mã đơn shop gửi hãng trùng mã đơn trên sàn. -#}
with s as (
    select * from {{ ref('int_union__shipments') }}
),

o as (
    select source_id, min(order_id) as order_id, min(channel_id) as channel_id
    from {{ ref('fct_order') }}
    group by source_id
)

select
    {{ dbt_utils.generate_surrogate_key(['s.source', 's.source_account', 's.source_id']) }} as shipment_id,
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    s.source as carrier,
    s.source_account,
    s.source_id as waybill,
    s.order_source_id,
    o.order_id,
    o.channel_id,
    s.status_raw,
    s.status,
    s.created_at,
    s.updated_at,
    s.ship_date,
    s.cod_vnd,
    s.shipping_fee_vnd,
    s.return_fee_vnd,
    s.insurance_fee_vnd,
    s.shipping_fee_vnd + s.return_fee_vnd + s.insurance_fee_vnd as total_fee_vnd
from s
left join o on o.source_id = s.order_source_id
