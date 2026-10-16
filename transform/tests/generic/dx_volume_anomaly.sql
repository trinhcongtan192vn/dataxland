{#- Bất thường khối lượng dữ liệu (FR-DQ-03) cho kho không chạy được Elementary (DuckDB ở local và CI).
Cùng ý tưởng `elementary.volume_anomalies`: số dòng của ngày hôm qua so với trung bình và độ lệch chuẩn của
28 ngày trước đó; lệch quá `sensitivity` độ lệch chuẩn thì lỗi. Dùng ở mức cảnh báo (docs/adr/0003). -#}
{% test dx_volume_anomaly(model, timestamp_column, sensitivity=3, days_back=28) %}
{%- set y = dbt.dateadd('day', -1, dx_today()) -%}
with daily as (
    select cast({{ timestamp_column }} as date) as d, count(*) as n
    from {{ model }}
    where cast({{ timestamp_column }} as date) >= cast({{ dbt.dateadd('day', -(days_back + 1), dx_today()) }} as date)
        and cast({{ timestamp_column }} as date) <= cast({{ y }} as date)
    group by 1
),

train as (
    select avg(cast(n as {{ dbt.type_float() }})) as mu, stddev_samp(cast(n as {{ dbt.type_float() }})) as sd, count(*) as k
    from daily
    where d < cast({{ y }} as date)
),

today_ as (
    select coalesce(max(n), 0) as n from daily where d = cast({{ y }} as date)
)

select today_.n as rows_yesterday, train.mu, train.sd
from today_ cross join train
where train.k >= 7 and train.sd > 0 and abs(today_.n - train.mu) > {{ sensitivity }} * train.sd
{% endtest %}
