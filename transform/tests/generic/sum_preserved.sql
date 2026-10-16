{#- Tổng `allocated_amount_vnd` theo `cost_id` bằng `amount_vnd` của `fct_cost`, sai lệch tối đa 1 đồng (FR-MOD-05). -#}
{% test sum_preserved(model, column_name, compare_model, compare_column, key='cost_id', tolerance=1) %}
with a as (
    select {{ key }}, sum({{ column_name }}) as allocated from {{ model }} group by {{ key }}
),

c as (
    select {{ key }}, sum({{ compare_column }}) as original from {{ compare_model }} group by {{ key }}
)

select
    coalesce(c.{{ key }}, a.{{ key }}) as {{ key }},
    c.original,
    a.allocated
from c
full outer join a on a.{{ key }} = c.{{ key }}
where abs(coalesce(c.original, 0) - coalesce(a.allocated, 0)) > {{ tolerance }}
{% endtest %}
