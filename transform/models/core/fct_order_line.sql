{#- Một sản phẩm trong một đơn (architecture §5.3). -#}
select
    order_line_id,
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    source,
    source_id,
    order_id,
    channel_id,
    order_date,
    product_id,
    seller_sku,
    item_name,
    quantity,
    unit_price_vnd,
    line_gross_vnd,
    allocated_discount_vnd as allocated_discount,
    allocated_discount_vnd,
    line_net_vnd,
    unit_cost_vnd,
    cogs_vnd,
    has_missing_cogs
from {{ ref('int_order_lines') }}
