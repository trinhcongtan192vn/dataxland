{#- Quy đổi tiền về VND theo tỷ giá chuyển khoản bán ra Vietcombank tại ngày giao dịch (FR-MOD-03, spec 02 §3.4).

`to_vnd(amount, currency, date)` dùng cột `rate_vnd` của bảng tỷ giá nối sẵn bằng `dx_fx_join(currency, date)`.
VND giữ nguyên; không có tỷ giá thì kết quả null và test not_null trên cột `*_vnd` chặn.
-#}
{% macro to_vnd(amount, currency, date_col, fx_alias='fx') -%}
    cast(case
        when {{ currency }} = 'VND' then cast({{ amount }} as numeric)
        else cast({{ amount }} as numeric) * {{ fx_alias }}.rate_vnd
    end as numeric)
{%- endmacro %}

{% macro dx_fx_join(currency, date_col, fx_alias='fx') -%}
    left join {{ ref('stg_fx__rates_daily') }} as {{ fx_alias }}
        on {{ fx_alias }}.currency = {{ currency }} and {{ fx_alias }}.date = {{ date_col }}
{%- endmacro %}

{#- Trạng thái chuẩn: dùng giá trị ghi đè của khách nếu có, nếu không thì seed (FR-MOD-01, FR-MOD-04). -#}
{% macro dx_status_joins(source_name, raw_col) -%}
    left join {{ ref('status_map__' ~ source_name) }} as sm on sm.status_raw = {{ raw_col }}
    left join {{ source('raw', 'dx__status_map_override') }} as so
        on so.source = '{{ source_name }}' and so.status_raw = {{ raw_col }}
{%- endmacro %}

{% macro dx_status_value() -%}
    cast(coalesce(so.status, sm.status) as {{ dbt.type_string() }})
{%- endmacro %}
