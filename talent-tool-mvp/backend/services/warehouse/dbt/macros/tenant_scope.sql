{#
  T2801 — 通用 helper macros
#}


{#
  安全的非空字符串 trim
#}
{% macro safe_trim(col) %}
  nullIf(trim({{ col }}), '')
{% endmacro %}


{#
  租户过滤: 给 dbt 生成 SQL 时自动注入 tenant_id
  用法: {{ tenant_filter('c.tenant_id') }}
  通过 dbt --vars '{tenant_id: ...}' 注入
#}
{% macro tenant_filter(default_col='tenant_id') %}
  {%- if var('tenant_id', none) -%}
    {{ default_col }} = '{{ var("tenant_id") }}'
  {%- else -%}
    1 = 1
  {%- endif -%}
{% endmacro %}


{#
  ClickHouse TTL: 1 年保留
#}
{% macro retention_ttl(days_var='retention_days') %}
  toDateTime(now()) + interval {{ var(days_var, 365) }} day
{% endmacro %}
