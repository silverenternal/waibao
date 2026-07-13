{{
  config(
    materialized='table',
    engine='MergeTree',
    order_by='(event_date, id)',
    partition_by='toYYYYMM(event_date)',
    tags=['marts', 'fact', 'matches']
  )
}}

-- T2801 fct_matches
-- 匹配事件事实表. 按天分区. 给漏斗 / 留存 / 渠道 ROI 用.
with m as (
  select
    toDate(matched_at) as event_date,
    id,
    candidate_id,
    job_id,
    tenant_id,
    channel,
    score,
    accepted,
    matched_at
  from {{ source('warehouse_raw', 'raw_matches') }}
)
select
  event_date,
  id,
  candidate_id,
  job_id,
  tenant_id,
  channel,
  score,
  cast(accepted as UInt8) as is_accepted,
  matched_at
from m
