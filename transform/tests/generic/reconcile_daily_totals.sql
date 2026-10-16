{#- Đối soát số đơn và doanh thu theo ngày với báo cáo tổng của nguồn (FR-DQ-02, spec 02 §6.2).

- So `fct_order` (đếm đơn, tổng `gross_amount_vnd` theo `order_date`, lọc theo `source`) với `stg_<source>__daily_totals`.
- Chỉ xét D-30 đến D-1.
- Lỗi khi |lệch| / số của nguồn × 100 > ngưỡng (`reconcile_tolerance_pct[source]` hoặc `default`, mặc định 1.0).
- Mỗi dòng lỗi: `source`, `date`, `metric`, `expected`, `actual`, `diff_pct`.
-#}
{% test reconcile_daily_totals(model, source_name) %}
{%- set tol_map = var('reconcile_tolerance_pct', {'default': 1.0}) -%}
{%- set tol = dx_get(tol_map, source_name, dx_get(tol_map, 'default', 1.0)) | float -%}
{%- set d0 = dbt.dateadd('day', -30, dx_today()) -%}
{%- set d1 = dbt.dateadd('day', -1, dx_today()) -%}
with actual as (
    select order_date as date, count(*) as order_count, sum(gross_amount_vnd) as gross_amount
    from {{ model }}
    where source = '{{ source_name }}'
        and order_date >= cast({{ d0 }} as date) and order_date <= cast({{ d1 }} as date)
    group by order_date
),

expected as (
    select date, sum(order_count) as order_count, sum(gross_amount_vnd) as gross_amount
    from {{ ref('stg_' ~ source_name ~ '__daily_totals') }}
    where date >= cast({{ d0 }} as date) and date <= cast({{ d1 }} as date)
    group by date
),

cmp as (
    select
        coalesce(e.date, a.date) as date,
        cast(coalesce(e.order_count, 0) as {{ dx_type_float() }}) as exp_count,
        cast(coalesce(a.order_count, 0) as {{ dx_type_float() }}) as act_count,
        cast(coalesce(e.gross_amount, 0) as {{ dx_type_float() }}) as exp_gross,
        cast(coalesce(a.gross_amount, 0) as {{ dx_type_float() }}) as act_gross
    from expected as e
    full outer join actual as a on a.date = e.date
),

rows_ as (
    select date, 'order_count' as metric, exp_count as expected, act_count as actual from cmp
    union all
    select date, 'gross_amount' as metric, exp_gross as expected, act_gross as actual from cmp
)

select
    '{{ source_name }}' as source,
    date,
    metric,
    expected,
    actual,
    round(cast(abs(actual - expected) * 100.0 / nullif(expected, 0) as {{ dbt.type_numeric() }}), 2) as diff_pct
from rows_
where (expected = 0 and actual <> 0)
    or (expected <> 0 and abs(actual - expected) * 100.0 / expected > {{ tol }})
{% endtest %}
