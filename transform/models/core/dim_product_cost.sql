{#- Giá vốn theo SKU với ngày hiệu lực; `valid_to` = `valid_from` của bản kế tiếp trừ 1 ngày (spec 02 §4). -#}
with c as (
    {% if 'portal' in var('sources', []) -%}
    select source_id, seller_sku, unit_cost_vnd, valid_from from {{ ref('stg_portal__product_costs') }} where not deleted
    {%- endif %}
    {% if 'portal' in var('sources', []) and 'portal_file' in var('sources', []) %}union all{% endif %}
    {% if 'portal_file' in var('sources', []) -%}
    select source_id, seller_sku, unit_cost_vnd, valid_from from {{ ref('stg_portal_file__product_costs') }} where not deleted
    {%- endif %}
    {% if 'portal' not in var('sources', []) and 'portal_file' not in var('sources', []) -%}
    select cast(null as {{ dbt.type_string() }}) as source_id, cast(null as {{ dbt.type_string() }}) as seller_sku,
        cast(null as numeric) as unit_cost_vnd, cast(null as date) as valid_from where 1 = 0
    {%- endif %}
),

d as (
    select *, row_number() over (partition by lower(trim(seller_sku)), valid_from order by source_id desc) as rn
    from c
)

select
    coalesce(ip.canonical_id, {{ dbt_utils.generate_surrogate_key(['lower(trim(d.seller_sku))']) }}) as product_id,
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    cast('portal' as {{ dbt.type_string() }}) as source,
    d.source_id,
    d.seller_sku,
    lower(trim(d.seller_sku)) as sku_key,
    d.valid_from,
    cast({{ dbt.dateadd('day', -1, 'lead(d.valid_from) over (partition by lower(trim(d.seller_sku)) order by d.valid_from)') }} as date) as valid_to,
    d.unit_cost_vnd
from d
left join {{ ref('int_identity__product') }} as ip on ip.sku_key = lower(trim(d.seller_sku))
where d.rn = 1
