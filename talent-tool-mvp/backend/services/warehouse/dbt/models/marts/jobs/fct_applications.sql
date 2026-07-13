{{
  config(
    materialized='table',
    engine='MergeTree',
    order_by='(event_date, id)',
    partition_by='toYYYYMM(event_date)',
    tags=['marts', 'fact', 'applications']
  )
}}

-- T2801 fct_applications
-- 投递事件. 给漏斗 (apply -> interview -> offer -> hire) 用.
with src as (
  select
    id,
    tenant_id,
    candidate_id,
    job_id,
    stage,
    toDate(created_at) as event_date,
    parseDateTime64(created_at, 6, 'UTC') as created_at,
    parseDateTime64(updated_at, 6, 'UTC') as updated_at,
    source_channel,
    referrer_id
  from {{ source('warehouse_raw', 'raw_applications') }}
)
select
  event_date,
  id,
  tenant_id,
  candidate_id,
  job_id,
  stage,
  source_channel,
  referrer_id,
  created_at,
  updated_at
from src
