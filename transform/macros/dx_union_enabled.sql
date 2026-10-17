{#- Ghép (UNION ALL) mọi model `stg_<source>__<object>` đang bật (spec 02 §1.3).

Model staging bật khi nguồn của nó có trong `var('sources')`, nên danh sách tính được ngay lúc parse và dbt suy ra
được phụ thuộc. Thêm nguồn mới: thêm thư mục staging và thêm nguồn vào `dx_staging_sources()`.
Không có nguồn nào: trả truy vấn rỗng với đúng cột của hợp đồng để core vẫn dựng được.
-#}
{% macro dx_staging_sources() -%}
    {{ return({
        'orders': ['shopee', 'tiktok_shop', 'lazada', 'amazon_seller', 'shopee_file', 'tiktok_shop_file', 'lazada_file'],
        'order_lines': ['shopee', 'tiktok_shop', 'lazada', 'amazon_seller', 'shopee_file', 'tiktok_shop_file', 'lazada_file'],
        'fees': ['shopee', 'tiktok_shop', 'lazada', 'amazon_seller', 'shopee_file', 'tiktok_shop_file', 'lazada_file'],
        'returns': ['shopee', 'tiktok_shop', 'lazada', 'amazon_seller', 'shopee_file', 'tiktok_shop_file', 'lazada_file'],
        'products': ['shopee', 'tiktok_shop', 'lazada', 'amazon_seller', 'shopee_file', 'tiktok_shop_file', 'lazada_file'],
        'ad_insights_daily': ['meta_ads', 'tiktok_ads', 'google_ads', 'amazon_ads', 'meta_ads_file', 'tiktok_ads_file',
                              'google_ads_file'],
        'daily_totals': ['shopee', 'tiktok_shop', 'lazada', 'amazon_seller'],
        'shipments': ['ghn', 'ghtk', 'jnt'],
    }) }}
{%- endmacro %}

{% macro dx_enabled_sources(object) -%}
    {%- set out = [] -%}
    {%- for s in dx_staging_sources()[object] if s in var('sources', []) -%}
        {%- do out.append(s) -%}
    {%- endfor -%}
    {{ return(out) }}
{%- endmacro %}

{% macro dx_union_enabled(object, columns) -%}
    {%- set srcs = dx_enabled_sources(object) -%}
    {%- if srcs | length == 0 -%}
        select {% for c, t in columns.items() %}cast(null as {{ t }}) as {{ c }}{% if not loop.last %}, {% endif %}{% endfor %}
        where 1 = 0
    {%- else -%}
        {%- for s in srcs %}
        select {% for c in columns.keys() %}{{ c }}{% if not loop.last %}, {% endif %}{% endfor %}
        from {{ ref('stg_' ~ s ~ '__' ~ object) }}
        {% if not loop.last %}union all{% endif %}
        {%- endfor -%}
    {%- endif -%}
{%- endmacro %}
