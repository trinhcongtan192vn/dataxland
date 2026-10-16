{#- Đơn đã gắn khóa chung: `order_id`, `channel_id`, `customer_id` (spec 02 §4). -#}
{{ config(materialized='table') }}

with o as (
    select * from {{ ref('int_union__orders') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['o.source', 'o.source_id']) }} as order_id,
    {{ dbt_utils.generate_surrogate_key(['o.source', 'o.source_account']) }} as channel_id,
    coalesce(
        ic.canonical_id,
        case
            when o.buyer_ref is not null then {{ dbt_utils.generate_surrogate_key(['o.source', 'o.buyer_ref']) }}
            when o.buyer_phone_hash is not null then {{ dbt_utils.generate_surrogate_key(['o.buyer_phone_hash']) }}
        end
    ) as customer_id,
    o.*
from o
left join {{ ref('int_identity__customer') }} as ic
    on ic.source = o.source and ic.source_id = o.source_id
