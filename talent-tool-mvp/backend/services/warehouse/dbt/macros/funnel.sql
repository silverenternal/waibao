{#
  T2801 — 漏斗宏
  给定一组 stage + boolean 表达式, 计算每阶段的人数 / 转化率.
  用法:
    {{ funnel(['applied', 'screened', 'interviewed', 'offered', 'hired'],
              'tenant_id', 'candidate_id') }}
#}
{% macro funnel(stages, partition_by, distinct_key) %}
  with funnel_data as (
    select
      {{ partition_by }} as _partition,
      {{ distinct_key }} as _key,
      {% for s in stages -%}
      max(if(stage = '{{ s }}', 1, 0)) as reached_{{ s }}{% if not loop.last %},{% endif %}
      {% endfor %}
    from {{ this }}
    group by _partition, _key
  ),
  funnel_agg as (
    select
      _partition,
      {% for s in stages -%}
      sum(reached_{{ s }}) as count_{{ s }}{% if not loop.last %},{% endif %}{% if not loop.last %},{% endif %}
      {% endfor %}
    from funnel_data
    group by _partition
  )
  select * from funnel_agg
{% endmacro %}


{#
  转化率 (相对上一阶段 + 相对首阶段). 输出 schema 保持平铺, 方便 BI 接入.
#}
{% macro funnel_conversion(stages) %}
  select
    {% for s in stages -%}
    count_{{ s }}{% if not loop.last %},{% endif %}
    {% endfor -%},
    {% for s in stages -%}
    {%- if not loop.first -%}
    round(count_{{ s }} / nullif(count_{{ stages[0] }}, 0), 4) as conv_from_first_{{ s }}{% if not loop.last %},{% endif %}
    {%- endif -%}
    {%- endfor -%}
    {%- for i in range(1, stages | length) -%}
    {%- set prev = stages[i-1] -%}
    {%- set cur = stages[i] -%}
    round(count_{{ cur }} / nullif(count_{{ prev }}, 0), 4) as conv_step_{{ i }}{% if not loop.last %},{% endif %}
    {%- endfor -%}
  from {{ this }}
{% endmacro %}
