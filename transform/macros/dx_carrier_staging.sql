{#- Staging vận đơn của hãng vận chuyển (FR-ING-09, spec 01 §9): bản ghi mới nhất của mỗi vận đơn, trạng thái chuẩn
qua seed `shipment_status_map`, số tiền VND (hãng nội địa chỉ tính VND). Chỉ trường vận đơn, không có người nhận. -#}
{% macro dx_carrier_staging(carrier) -%}
with s as (
    select * from (
        select *, row_number() over (partition by _dx_source_account, waybill order by _dx_loaded_at desc) as rn
        from {{ source('raw', carrier ~ '__shipments') }}
    ) as src where rn = 1
),

m as (
    select status_raw, status from {{ ref('shipment_status_map') }} where carrier = '{{ carrier }}'
)

select
    cast('{{ carrier }}' as {{ dbt.type_string() }}) as source,
    {{ dx_str('s.waybill') }} as source_id,
    {{ dx_str('s._dx_source_account') }} as source_account,
    {{ dx_str('s.client_order_code') }} as order_source_id,
    {{ dx_str('s.status_raw') }} as status_raw,
    m.status,
    {{ dx_ts('s.created_at') }} as created_at,
    {{ dx_ts('s.updated_at') }} as updated_at,
    {{ dx_vn_date(dx_ts('s.created_at')) }} as ship_date,
    coalesce({{ dx_num('s.cod_amount') }}, 0) as cod_vnd,
    coalesce({{ dx_num('s.shipping_fee') }}, 0) as shipping_fee_vnd,
    coalesce({{ dx_num('s.return_fee') }}, 0) as return_fee_vnd,
    coalesce({{ dx_num('s.insurance_fee') }}, 0) as insurance_fee_vnd
from s
left join m on lower(trim({{ dx_str('s.status_raw') }})) = lower(m.status_raw)
{%- endmacro %}
