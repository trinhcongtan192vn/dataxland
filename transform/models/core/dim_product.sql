{#- Một SKU sau khi ghép xuyên kênh. GĐ1: khóa theo `seller_sku` chuẩn hóa; GĐ2 áp `identity_map` (spec 02 §4). -#}
with cand as (
    select source, source_id, seller_sku, name, barcode, category_raw, 1 as prio from {{ ref('int_union__products') }}
    union all
    select source, source_id, seller_sku, item_name as name, cast(null as {{ dbt.type_string() }}) as barcode,
        cast(null as {{ dbt.type_string() }}) as category_raw, 2 as prio
    from {{ ref('int_union__order_lines') }}
),

keyed as (
    select
        cand.*,
        lower(trim(seller_sku)) as sku_key,
        case
            when nullif(trim(seller_sku), '') is not null then {{ dbt_utils.generate_surrogate_key(['lower(trim(seller_sku))']) }}
            else {{ dbt_utils.generate_surrogate_key(['source', 'source_id']) }}
        end as base_id
    from cand
),

mapped as (
    select k.*, coalesce(ip.canonical_id, k.base_id) as product_id
    from keyed as k
    left join {{ ref('int_identity__product') }} as ip on ip.sku_key = k.sku_key
),

ranked as (
    select
        mapped.*,
        max(barcode) over (partition by product_id) as any_barcode,
        max(category_raw) over (partition by product_id) as any_category,
        row_number() over (partition by product_id order by prio, source, source_id) as rn
    from mapped
)

select
    product_id,
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    source,
    source_id,
    seller_sku,
    name as canonical_name,
    any_category as category,
    any_barcode as barcode
from ranked
where rn = 1
