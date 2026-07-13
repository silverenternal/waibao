{{
  config(
    materialized='view',
    tags=['staging', 'jobs']
  )
}}

-- T2801 stg_jobs
with src as (
  select
    id,
    tenant_id,
    company_id,
    nullIf(trim(title), '') as title,
    lower(coalesce(industry, '')) as industry,
    lower(coalesce(city, '')) as city,
    lower(coalesce(country, '')) as country,
    salary_min,
    salary_max,
    experience_min,
    experience_max,
    status,
    parseDateTime64(updated_at, 6, 'UTC') as updated_at,
    parseDateTime64(created_at, 6, 'UTC') as created_at,
    parseDateTime64(closed_at, 6, 'UTC') as closed_at,
    now() as _ingested_at
  from {{ source('warehouse_raw', 'raw_jobs') }}
  where id is not null
)

select * from src
