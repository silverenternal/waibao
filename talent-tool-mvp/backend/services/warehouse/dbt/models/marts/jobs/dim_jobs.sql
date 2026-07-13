{{
  config(
    materialized='table',
    engine='ReplacingMergeTree',
    order_by='id',
    partition_by='toYYYYMM(_ingested_at)',
    tags=['marts', 'dimension', 'jobs']
  )
}}

-- T2801 dim_jobs
with s as (
  select * from {{ ref('stg_jobs') }}
)
select
  s.*,
  if(closed_at is null, null, dateDiff('day', created_at, closed_at)) as time_to_close_days,
  if(salary_min is not null and salary_max is not null, (salary_min + salary_max) / 2, null) as salary_midpoint,
  if(status in ('open', 'paused'), 1, 0) as is_open
from s
