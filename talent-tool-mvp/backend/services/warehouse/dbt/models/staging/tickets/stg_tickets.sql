{{
  config(
    materialized='view',
    tags=['staging', 'tickets']
  )
}}

-- T2801 stg_tickets (客服工单)
with src as (
  select
    id,
    tenant_id,
    reporter_id,
    assignee_id,
    category,
    priority,
    status,
    subject,
    parseDateTime64(created_at, 6, 'UTC') as created_at,
    parseDateTime64(first_response_at, 6, 'UTC') as first_response_at,
    parseDateTime64(resolved_at, 6, 'UTC') as resolved_at,
    parseDateTime64(closed_at, 6, 'UTC') as closed_at,
    parseDateTime64(updated_at, 6, 'UTC') as updated_at,
    sla_target_hours,
    now() as _ingested_at
  from {{ source('warehouse_raw', 'raw_tickets') }}
  where id is not null
)

select * from src
