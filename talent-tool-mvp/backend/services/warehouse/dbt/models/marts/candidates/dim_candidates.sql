{{
  config(
    materialized='table',
    engine='ReplacingMergeTree',
    order_by='id',
    partition_by='toYYYYMM(_ingested_at)',
    tags=['marts', 'dimension', 'candidates']
  )
}}

-- T2801 dim_candidates
-- 候选人维度表: 给 BI / API 用. ReplacingMergeTree 让更新幂等.
-- 比 stg 多:
--   * tenure_days / age_bucket
--   * skills_count
--   * is_active_30d
--   * last_touch_at

with s as (
  select * from {{ ref('stg_candidates') }}
),
enriched as (
  select
    s.*,
    length(s.skills) as skills_count,
    case
      when s.experience_years is null then 'unknown'
      when s.experience_years < 2 then 'junior'
      when s.experience_years < 5 then 'mid'
      when s.experience_years < 10 then 'senior'
      else 'principal'
    end as experience_band,
    greatest(s.updated_at, s.created_at) as last_touch_at,
    if(s.updated_at >= now() - interval 30 day, 1, 0) as is_active_30d,
    if(s.updated_at >= now() - interval 90 day, 1, 0) as is_active_90d
  from s
)
select * from enriched
