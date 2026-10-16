{{ config(enabled='portal' in var('sources', [])) }}
{#- Giá vốn khách nhập trên cổng (spec 01 §7, spec 02 §3.2). Bản ghi xóa mềm được giữ với `deleted = true`. -#}
with src as (
    select *, row_number() over (partition by id order by _dx_loaded_at desc) as rn
    from {{ source('raw', 'portal__product_costs') }}
    where {{ dx_str('tenant_id') }} = '{{ var("tenant_id") }}'
)

select
    {{ dx_str('id') }} as source_id,
    trim({{ dx_str('seller_sku') }}) as seller_sku,
    {{ dx_num('unit_cost_vnd') }} as unit_cost_vnd,
    cast(valid_from as date) as valid_from,
    (deleted_at is not null) as deleted
from src
where rn = 1
