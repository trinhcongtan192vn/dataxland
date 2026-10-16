{#- Macro đa nền tảng dùng trong core và marts (spec 02 §7, NFR-07). -#}

{#- Ngày nghiệp vụ theo giờ Việt Nam từ timestamp UTC. Việt Nam không có giờ mùa hè nên cộng 7 giờ là chính xác. -#}
{% macro dx_vn_date(ts) -%}
    cast({{ dbt.dateadd('hour', 7, ts) }} as date)
{%- endmacro %}

{#- "Hôm nay" theo giờ Việt Nam: lấy từ biến `today` do Dagster truyền (để chạy lại được), nếu không thì từ giờ hệ thống. -#}
{% macro dx_today() -%}
    {%- if var('today', none) -%}
        cast('{{ var("today") }}' as date)
    {%- else -%}
        {{ dx_vn_date(dx_now()) }}
    {%- endif -%}
{%- endmacro %}

{% macro dx_div(a, b) -%}
    ({{ a }}) / nullif({{ b }}, 0)
{%- endmacro %}

{% macro dx_tenant() -%}
    cast('{{ var("tenant_id") }}' as {{ dbt.type_string() }})
{%- endmacro %}

{#- Thời điểm hiện tại theo UTC, kiểu timestamp không múi giờ (spec 00 §3.2). -#}
{% macro dx_now() -%}
    {{ return(adapter.dispatch('dx_now', 'dx')()) }}
{%- endmacro %}
{% macro default__dx_now() -%}
    cast({{ dbt.current_timestamp() }} as {{ dbt.type_timestamp() }})
{%- endmacro %}
{% macro duckdb__dx_now() -%}
    cast(timezone('UTC', current_timestamp) as timestamp)
{%- endmacro %}

{% macro dx_bool(v) -%}
    {%- if v -%} (1 = 1) {%- else -%} (1 = 0) {%- endif -%}
{%- endmacro %}

{#- Ngày cuối tháng: ngày đầu tháng kế tiếp trừ 1. -#}
{% macro dx_month_end(month_start) -%}
    cast({{ dbt.dateadd('day', -1, dbt.dateadd('month', 1, month_start)) }} as date)
{%- endmacro %}


{#- ---------------- Macro chỉ dùng ở staging (được phép dùng hàm riêng của từng kho, NFR-07) ---------------- -#}

{% macro dx_from_unix(col) -%}
    {{ return(adapter.dispatch('dx_from_unix', 'dx')(col)) }}
{%- endmacro %}
{% macro default__dx_from_unix(col) -%}
    cast(to_timestamp(cast({{ col }} as bigint)) at time zone 'UTC' as timestamp)
{%- endmacro %}
{% macro bigquery__dx_from_unix(col) -%}
    timestamp_seconds(cast({{ col }} as int64))
{%- endmacro %}

{#- Chuỗi giờ địa phương `YYYY-MM-DD HH:MM:SS +0700` (Lazada) → timestamp UTC. -#}
{% macro dx_from_local_vn(col) -%}
    {{ dbt.dateadd('hour', -7, 'cast(substr(' ~ col ~ ', 1, 19) as ' ~ dbt.type_timestamp() ~ ')') }}
{%- endmacro %}

{% macro dx_sha256_hex(expr) -%}
    {{ return(adapter.dispatch('dx_sha256_hex', 'dx')(expr)) }}
{%- endmacro %}
{% macro default__dx_sha256_hex(expr) -%}
    sha256({{ expr }})
{%- endmacro %}
{% macro bigquery__dx_sha256_hex(expr) -%}
    to_hex(sha256({{ expr }}))
{%- endmacro %}

{% macro dx_regexp_replace(expr, pattern, repl) -%}
    {{ return(adapter.dispatch('dx_regexp_replace', 'dx')(expr, pattern, repl)) }}
{%- endmacro %}
{% macro default__dx_regexp_replace(expr, pattern, repl) -%}
    regexp_replace({{ expr }}, '{{ pattern }}', '{{ repl }}', 'g')
{%- endmacro %}
{% macro bigquery__dx_regexp_replace(expr, pattern, repl) -%}
    regexp_replace({{ expr }}, r'{{ pattern }}', '{{ repl }}')
{%- endmacro %}

{% macro dx_num(col) -%}
    cast(cast({{ col }} as {{ dbt.type_string() }}) as numeric)
{%- endmacro %}

{% macro dx_str(col) -%}
    cast({{ col }} as {{ dbt.type_string() }})
{%- endmacro %}

{% macro dx_ts(col) -%}
    cast({{ col }} as {{ dbt.type_timestamp() }})
{%- endmacro %}

{#- Lấy giá trị từ map biến dbt (kể cả map truyền qua `overrides` của unit test). -#}
{% macro dx_get(d, key, default=none) -%}
    {%- if d is mapping and key in d -%}{{ return(d[key]) }}{%- else -%}{{ return(default) }}{%- endif -%}
{%- endmacro %}

{#- Số thực 8 byte (DuckDB `float` chỉ 4 byte). -#}
{% macro dx_type_float() -%}
    {{ return(adapter.dispatch('dx_type_float', 'dx')()) }}
{%- endmacro %}
{% macro default__dx_type_float() -%}double{%- endmacro %}
{% macro bigquery__dx_type_float() -%}float64{%- endmacro %}
