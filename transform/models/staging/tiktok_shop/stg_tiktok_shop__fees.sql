{{ config(enabled='tiktok_shop' in var('sources', [])) }}
{#- Phí TikTok Shop từ statement transactions (spec 01 §4). -#}
with s as (
    select * from (
        select *, row_number() over (partition by order_id, transaction_id order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'tiktok_shop__settlements') }}
    ) as src where rn = 1
),

u as (
    {% for fee in ['platform_commission', 'transaction_fee', 'shipping_cost', 'affiliate_commission'] %}
    select
        s.order_id, s.transaction_id, s._dx_source_account, s.currency,
        {{ dx_vn_date(dx_from_unix('s.statement_time')) }} as fee_date,
        '{{ fee }}' as fee_type_raw,
        {{ dx_num('s.' ~ fee ~ '_amount') }} as amount_o
    from s
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

select
    cast('tiktok_shop' as {{ dbt.type_string() }}) as source,
    {{ dbt.concat([dx_str('u.transaction_id'), "'-'", 'u.fee_type_raw']) }} as source_id,
    {{ dx_str('u.order_id') }} as order_source_id,
    {{ dx_str('u._dx_source_account') }} as source_account,
    u.fee_date,
    cast(u.fee_type_raw as {{ dbt.type_string() }}) as fee_type_raw,
    cast(ft.cost_type as {{ dbt.type_string() }}) as cost_type,
    cast(u.amount_o as numeric) as amount_original,
    {{ dx_str('u.currency') }} as currency,
    {{ to_vnd('u.amount_o', 'u.currency', 'u.fee_date') }} as amount_vnd
from u
left join {{ ref('fee_type_map__tiktok_shop') }} as ft on ft.fee_type_raw = u.fee_type_raw
{{ dx_fx_join('u.currency', 'u.fee_date') }}
where u.amount_o <> 0 and coalesce(ft.cost_type, '') <> 'exclude'
