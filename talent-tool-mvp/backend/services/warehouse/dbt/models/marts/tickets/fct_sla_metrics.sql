{{
  config(
    materialized='table',
    engine='AggregatingMergeTree',
    order_by='(event_date, tenant_id, priority)',
    partition_by='toYYYYMM(event_date)',
    tags=['marts', 'fact', 'sla', 'tickets']
  )
}}

-- T2801 fct_sla_metrics
-- 预聚合的 SLA 指标. 用 AggregatingMergeTree 让实时增量聚合.
-- 一天一行, 减少查询时扫描量.
with t as (
  select * from {{ ref('stg_tickets') }}
),
computed as (
  select
    toDate(created_at) as event_date,
    tenant_id,
    priority,
    id,
    status,
    sla_target_hours,
    if(first_response_at is not null,
       dateDiff('minute', created_at, first_response_at), null) as first_response_minutes,
    if(resolved_at is not null,
       dateDiff('minute', created_at, resolved_at), null) as resolution_minutes,
    if(sla_target_hours is not null and first_response_at is not null,
       first_response_at <= created_at + interval sla_target_hours hour, null) as is_first_response_within_sla
  from t
)
select
  event_date,
  tenant_id,
  priority,
  countState() as ticket_count,
  countState(if(status = 'resolved', 1, null)) as resolved_count,
  countState(if(is_first_response_within_sla, 1, null)) as sla_met_count,
  avgState(first_response_minutes) as avg_first_response_min,
  avgState(resolution_minutes) as avg_resolution_min,
  quantileState(0.95)(first_response_minutes) as p95_first_response_min,
  quantileState(0.95)(resolution_minutes) as p95_resolution_min
from computed
group by event_date, tenant_id, priority
