{#
  T2801 — 留存 cohort 宏
  计算第 1/7/14/30/60/90 天的留存率. 走 ClickHouse retention() 函数.
#}
{% macro retention_cohort(first_event_at, repeat_event_at, cohort_granularity='month', periods=(1, 7, 14, 30, 60, 90)) %}
  {%- set start = time_bucket(first_event_at, cohort_granularity) -%}
  select
    {{ start }} as cohort,
    uniqState({{ first_event_at | replace('updated_at', 'user_id') }}) as cohort_size,
    {% for p in periods -%}
    uniqState(if(
      dateDiff('day', first_event_at, repeat_event_at) = {{ p }},
      repeat_event_at, null
    )) as retained_d{{ p }}{% if not loop.last %},{% endif %}
    {% endfor %}
  from {{ this }}
  group by cohort
{% endmacro %}


{#
  简单版留存查询模板: 给 BI / API 用.
#}
{% macro retention_query(first_event_at, repeat_event_at, periods=(1, 7, 14, 30, 60, 90)) %}
  with base as (
    select
      {{ first_event_at }} as first_at,
      {{ repeat_event_at }} as repeat_at
    from {{ this }}
    where {{ first_event_at }} is not null
  )
  select
    toDate(first_at) as cohort_day,
    count(distinct first_at) as cohort_size,
    {% for p in periods -%}
    count(distinct if(dateDiff('day', first_at, repeat_at) = {{ p }}, repeat_at, null)) as retained_d{{ p }}{% if not loop.last %},{% endif %}
    {% endfor %}
  from base
  where repeat_at >= first_at
  group by cohort_day
  order by cohort_day
{% endmacro %}
