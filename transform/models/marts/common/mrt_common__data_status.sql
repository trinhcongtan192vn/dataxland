{#- Một dòng: thời điểm dữ liệu (min theo nguồn của `max(_dx_loaded_at)`), tỷ lệ doanh thu tạm tính và SKU thiếu giá
vốn trong 30 ngày (spec 02 §5, spec 03 §4.3). -#}
{%- set main = {
    'shopee': 'orders', 'tiktok_shop': 'orders', 'lazada': 'orders', 'amazon_seller': 'orders',
    'meta_ads': 'ad_insights_daily', 'tiktok_ads': 'ad_insights_daily', 'google_ads': 'ad_insights_daily',
    'amazon_ads': 'ad_insights_daily', 'shopee_file': 'orders', 'tiktok_shop_file': 'orders', 'lazada_file': 'orders',
    'meta_ads_file': 'ad_insights_daily', 'tiktok_ads_file': 'ad_insights_daily', 'google_ads_file': 'ad_insights_daily',
} %}
{%- set srcs = [] %}
{%- for s in var('sources', []) if s in main %}{% do srcs.append(s) %}{% endfor %}
{%- set since = dbt.dateadd('day', -30, dx_today()) %}
with loads as (
    {%- if srcs | length == 0 %}
    select cast(null as {{ dbt.type_timestamp() }}) as max_loaded
    {%- else %}
    {%- for s in srcs %}
    select max(cast(_dx_loaded_at as {{ dbt.type_timestamp() }})) as max_loaded
    from {{ source('raw', s ~ '__' ~ main[s]) }}
    {% if not loop.last %}union all{% endif %}
    {%- endfor %}
    {%- endif %}
),

rev as (
    select
        sum(case when o.is_provisional then r.net_revenue_vnd else 0 end) as prov,
        sum(r.net_revenue_vnd) as total
    from {{ ref('fct_order') }} as o
    inner join {{ ref('int_order_revenue') }} as r on r.order_id = o.order_id
    where o.order_date >= cast({{ since }} as date) and o.order_date < {{ dx_today() }}
),

miss as (
    select
        count(distinct lower(trim(l.seller_sku))) as sku_count,
        sum(l.line_net_vnd) as revenue
    from {{ ref('fct_order_line') }} as l
    inner join {{ ref('fct_order') }} as o on o.order_id = l.order_id
    where l.has_missing_cogs and not o.is_cancelled
        and l.order_date >= cast({{ since }} as date) and l.order_date < {{ dx_today() }}
)

select
    {{ dx_tenant() }} as tenant_id,
    {{ dx_now() }} as _dx_updated_at,
    (select min(max_loaded) from loads) as data_as_of,
    cast(coalesce({{ dx_div('rev.prov', 'rev.total') }}, 0) as numeric) as provisional_revenue_share,
    coalesce(miss.sku_count, 0) as missing_cogs_sku_count,
    cast(coalesce(miss.revenue, 0) as numeric) as missing_cogs_revenue_vnd,
    '{{ var("run_id", "local") }}' as run_id
from rev
cross join miss
