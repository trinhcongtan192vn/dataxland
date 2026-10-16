{#- Một lần trả hoặc hủy một dòng đơn (architecture §5.3). -#}
select
    {{ dbt_utils.generate_surrogate_key(['r.source', 'r.source_id']) }} as return_id,
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    r.source,
    r.source_id,
    {{ dbt_utils.generate_surrogate_key(['r.source', 'r.order_source_id']) }} as order_id,
    case when r.order_line_source_id is not null then {{ dbt_utils.generate_surrogate_key(['r.source', 'r.order_line_source_id']) }} end as order_line_id,
    r.returned_at,
    r.return_date,
    r.reason,
    r.reason_raw,
    r.refund_amount_vnd,
    r.return_fee_vnd,
    r.status
from {{ ref('int_union__returns') }} as r
