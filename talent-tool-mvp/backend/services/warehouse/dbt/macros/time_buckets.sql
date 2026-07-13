{#
  T2801 — 时间分桶宏
  按传入的 granularity 截断到 day/week/month/quarter/year/hour.
  用法: {{ time_bucket('created_at', 'day') }} as event_date
#}
{% macro time_bucket(column, granularity='day') %}
  {%- if granularity == 'hour' -%}
    toStartOfHour({{ column }})
  {%- elif granularity == 'day' -%}
    toDate({{ column }})
  {%- elif granularity == 'week' -%}
    toStartOfWeek({{ column }})
  {%- elif granularity == 'month' -%}
    toStartOfMonth({{ column }})
  {%- elif granularity == 'quarter' -%}
    toStartOfQuarter({{ column }})
  {%- elif granularity == 'year' -%}
    toStartOfYear({{ column }})
  {%- else -%}
    toDate({{ column }})
  {%- endif -%}
{% endmacro %}


{#
  给 SQL 自动展开成多列. 用法:
    {{ time_buckets('event_at', ['day', 'week', 'month']) }}
  会生成: event_at_day, event_at_week, event_at_month
#}
{% macro time_buckets(column, granularities) %}
  {%- set cols = [] -%}
  {%- for g in granularities -%}
    {%- set _ = cols.append("'" ~ g ~ "' as " ~ column ~ "_" ~ g) -%}
  {%- endfor -%}
  {{ cols | join(', ') }}
{% endmacro %}
