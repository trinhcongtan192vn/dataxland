{#- Tỷ giá theo ngày, điền mọi ngày từ ngày sớm nhất có tỷ giá đến hôm nay; ngày trống (cuối tuần, lễ) lấy tỷ giá
của ngày gần nhất trước đó (FR-MOD-03, spec 02 §3.2). Tỷ giá nhập tay (`source = manual`) được ưu tiên. -#}
with rates as (
    select
        cast(date as date) as rate_date,
        upper({{ dx_str('currency') }}) as currency,
        {{ dx_num('rate_vnd') }} as rate_vnd,
        case when {{ dx_str('source') }} = 'manual' then 0 else 1 end as prio
    from {{ source('dx_ref', 'fx_rates') }}
),

best as (
    select rate_date, currency, rate_vnd
    from (
        select *, row_number() over (partition by rate_date, currency order by prio) as rn
        from rates
    ) as r
    where rn = 1
),

spine as (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="(select min(cast(date as date)) from " ~ source('dx_ref', 'fx_rates') ~ ")",
        end_date=dbt.dateadd('day', 1, dx_today())
    ) }}
),

filled as (
    select
        cast(s.date_day as date) as date,
        b.currency,
        b.rate_vnd,
        row_number() over (partition by s.date_day, b.currency order by b.rate_date desc) as rn
    from spine as s
    inner join best as b on b.rate_date <= cast(s.date_day as date)
)

select
    date,
    cast(currency as {{ dbt.type_string() }}) as currency,
    cast(rate_vnd as numeric) as rate_vnd
from filled
where rn = 1
