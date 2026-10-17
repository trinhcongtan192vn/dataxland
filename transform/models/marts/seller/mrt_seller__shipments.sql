{{ config(enabled=var('pack') in ['seller']) }}
{#- Vận đơn theo ngày gửi, hãng, trạng thái (FR-ING-09): phí vận chuyển, phí hoàn, COD theo vận đơn của hãng. -#}
select
    shipment_id,
    tenant_id,
    _dx_updated_at,
    ship_date,
    carrier,
    status,
    waybill,
    order_id,
    case when order_id is null then false else true end as matched_order,
    cod_vnd,
    shipping_fee_vnd,
    return_fee_vnd,
    insurance_fee_vnd,
    total_fee_vnd
from {{ ref('fct_shipment') }}
