{{
  config(
    materialized='view',
    tags=['staging', 'candidates']
  )
}}

-- T2801 stg_candidates
-- 1:1 映射 raw_candidates, 类型规整 + 加 audit 字段.
-- 这是 dim / fct 的唯一来源, 不要在这里做 join.

with src as (
  select
    id,
    nullIf(trim(email), '') as email,
    nullIf(trim(full_name), '') as full_name,
    nullIf(trim(phone), '') as phone,
    coalesce(skills, []) as skills,
    lower(coalesce(country, '')) as country,
    lower(coalesce(city, '')) as city,
    experience_years,
    education_level,
    expected_salary,
    status,
    tenant_id,
    parseDateTime64(updated_at, 6, 'UTC') as updated_at,
    parseDateTime64(created_at, 6, 'UTC') as created_at,
    now() as _ingested_at,
    _airbyte_emitted_at
  from {{ source('warehouse_raw', 'raw_candidates') }}
  where id is not null
)

select * from src
