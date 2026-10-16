{{ config(enabled='portal' in var('sources', [])) }}
{#- Ngân sách quảng cáo theo tháng và nền tảng khách nhập trên cổng (spec 01 §7, spec 02 §3.2). -#}
with src as (
    select *, row_number() over (partition by id order by _dx_loaded_at desc) as rn
    from {{ source('raw', 'portal__ad_budgets') }}
    where {{ dx_str('tenant_id') }} = '{{ var("tenant_id") }}'
)

select
    {{ dx_str('id') }} as source_id,
    {{ dx_str('platform') }} as platform,
    cast({{ dbt.date_trunc('month', 'cast(month as date)') }} as date) as month,
    {{ dx_num('budget_vnd') }} as budget_vnd,
    (deleted_at is not null) as deleted
from src
where rn = 1
