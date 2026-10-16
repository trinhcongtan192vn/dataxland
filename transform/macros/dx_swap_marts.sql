{#- Hoán đổi marts: `<mart>__staging` → `<mart>` khi mọi test chặn đã qua (spec 02 §6.3, spec 04 §3.2).
Gọi bằng `dbt run-operation dx_swap_marts`. Khi bị chặn, bước này không chạy nên Cube vẫn đọc marts cũ. -#}
{% macro dx_swap_marts() -%}
    {%- set schema = var('dataset_prefix') ~ '_marts' -%}
    {%- set names = [] -%}
    {%- for node in graph.nodes.values() -%}
        {%- if node.resource_type == 'model' and node.fqn | length > 1 and node.fqn[1] == 'marts' and node.config.enabled -%}
            {%- do names.append(node.name) -%}
        {%- endif -%}
    {%- endfor -%}
    {%- for name in names | sort -%}
        {%- set staging = adapter.get_relation(database=target.database, schema=schema, identifier=name ~ '__staging') -%}
        {%- if staging is not none -%}
            {%- do adapter.dispatch('dx_swap_one', 'dx')(schema, name) -%}
            {{ log('swap ' ~ schema ~ '.' ~ name, info=true) }}
        {%- endif -%}
    {%- endfor -%}
{%- endmacro %}

{% macro default__dx_swap_one(schema, name) -%}
    {%- set sql -%}
        drop table if exists "{{ schema }}"."{{ name }}";
        alter table "{{ schema }}"."{{ name }}__staging" rename to "{{ name }}";
    {%- endset -%}
    {%- do run_query(sql) -%}
    {%- do adapter.commit() -%}
{%- endmacro %}

{% macro bigquery__dx_swap_one(schema, name) -%}
    {%- set sql -%}
        create or replace table `{{ target.project }}.{{ schema }}.{{ name }}` copy `{{ target.project }}.{{ schema }}.{{ name }}__staging`;
        drop table `{{ target.project }}.{{ schema }}.{{ name }}__staging`;
    {%- endset -%}
    {%- do run_query(sql) -%}
{%- endmacro %}
