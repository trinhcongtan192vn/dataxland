{{ config(enabled='amazon_seller' in var('sources', [])) }}
{#- Tổng theo ngày lấy từ đường độc lập với chi tiết đơn, dùng cho test đối soát (spec 01 §1.1). -#}
with t as (
    select * from (
        select *, row_number() over (partition by date, _dx_source_account order by _dx_loaded_at desc) as rn
        from {{ source('raw', 'amazon_seller__daily_totals') }}
    ) as src where rn = 1
)

select
    cast('amazon_seller' as {{ dbt.type_string() }}) as source,
    {{ dx_str('t._dx_source_account') }} as source_account,
    cast(t.date as date) as date,
    cast(t.order_count as bigint) as order_count,
    {{ to_vnd('t.gross_amount', 't.currency', 'cast(t.date as date)') }} as gross_amount_vnd
from t
{{ dx_fx_join('t.currency', 'cast(t.date as date)') }}
