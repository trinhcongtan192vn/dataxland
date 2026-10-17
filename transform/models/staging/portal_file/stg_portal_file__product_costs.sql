{{ config(enabled='portal_file' in var('sources', [])) }}
{#- Giá vốn từ file mẫu trong lượt kiểm tra sức khỏe (spec 07 §4.1). -#}
select
    {{ dx_str('id') }} as source_id,
    trim({{ dx_str('seller_sku') }}) as seller_sku,
    {{ dx_num('unit_cost_vnd') }} as unit_cost_vnd,
    cast(valid_from as date) as valid_from,
    false as deleted
from {{ source('raw', 'portal_file__product_costs') }}
