{#- Băm thông tin cá nhân người mua (NFR-03, spec 02 §3.5). Chỉ dùng ở staging.

- `phone`: bỏ ký tự không phải số, đổi đầu `84` thành `0`, rồi băm.
- `email`: cắt khoảng trắng, chữ thường, rồi băm.
- SHA-256 hex của `salt || value`, `salt` từ `env_var('DX_PII_SALT')`.
- Giá trị rỗng hoặc bị sàn che (chứa `*`): null.
-#}
{% macro pii_hash(column, kind) -%}
    {%- set salt = env_var('DX_PII_SALT', '') -%}
    {%- if kind == 'phone' -%}
        {%- set digits = dx_regexp_replace(dx_str(column), '[^0-9]', '') -%}
        {%- set norm = "case when " ~ digits ~ " like '84%' then " ~ dbt.concat(["'0'", "substr(" ~ digits ~ ", 3)"]) ~ " else " ~ digits ~ " end" -%}
    {%- else -%}
        {%- set norm = "lower(trim(" ~ dx_str(column) ~ "))" -%}
    {%- endif -%}
    case
        when {{ column }} is null or trim({{ dx_str(column) }}) = '' or {{ dx_str(column) }} like '%*%' then null
        else {{ dx_sha256_hex(dbt.concat(["'" ~ salt ~ "'", norm])) }}
    end
{%- endmacro %}
