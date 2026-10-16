{#- Dataset theo lớp: `<dataset_prefix>_<layer>` (spec 02 §1.2). Seed nằm trong `_core`, test lưu lỗi trong `_audit`. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set prefix = var('dataset_prefix') -%}
    {%- if custom_schema_name is none -%}
        {{ prefix }}_core
    {%- else -%}
        {{ prefix }}_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}


{#- Marts được dựng vào bảng `<tên>__staging`; bước `swap_marts` đổi tên sau khi mọi test chặn qua (spec 02 §6.3). -#}
{% macro generate_alias_name(custom_alias_name=none, node=none) -%}
    {%- set base = custom_alias_name | trim if custom_alias_name else node.name -%}
    {%- if node.resource_type == 'model' and node.fqn | length > 1 and node.fqn[1] == 'marts' -%}
        {{ base }}__staging
    {%- else -%}
        {{ base }}
    {%- endif -%}
{%- endmacro %}


{% macro dx_query_comment(node) -%}
    {%- set labels = {'tenant_id': var('tenant_id'), 'dx_job': 'dbt', 'run_id': var('run_id', 'local') | string | lower | replace(':', '-')} -%}
    {{ tojson(labels) }}
{%- endmacro %}
