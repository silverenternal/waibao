{{
  config(
    materialized='view',
    tags=['intermediate', 'matches']
  )
}}

-- T2801 — match 事件 join candidate + job, 方便 fct 计算
with matches as (
  select * from {{ ref('stg_matches') if false else 'stg_matches' }}
)
-- 注: 真实项目里 matches 来源是 raw_matches, 这里简化. 真实 ETL 时
-- 把 raw_matches 转成 stg_matches 然后 join.
select
  m.id as match_id,
  m.candidate_id,
  m.job_id,
  m.score,
  m.matched_at,
  m.accepted,
  c.country as candidate_country,
  c.experience_years,
  j.industry,
  j.country as job_country
from {{ source('warehouse_raw', 'raw_matches') }} m
left join {{ ref('stg_candidates') }} c on c.id = m.candidate_id
left join {{ ref('stg_jobs') }} j on j.id = m.job_id
