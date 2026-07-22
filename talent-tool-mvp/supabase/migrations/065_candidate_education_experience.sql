-- v11.4 — Add `education` + `experience_years` columns to candidates.
--
-- 001_cloud_schema.sql's candidates table only has skills/experience as JSONB;
-- it has no top-level `education` / `experience_years` columns. But:
--   * seed_test_data.py writes both fields per candidate;
--   * _candidate_to_card reads row.get("education") / row.get("experience_years");
--   * hard_filter._check_education reads candidate.education as a HARD condition
--     (合同: 学历 = 硬条件必须满足).
-- Without these columns the seed loader silently drops them → HR cards render
-- blank education, and the education hard-condition always sees None (空约束 →
-- 满分), making it inert. This migration adds the columns so seed data persists
-- and the education gate is a real signal.
--
-- Idempotent (ADD COLUMN IF NOT EXISTS) — safe on fresh + existing volumes.

BEGIN;

ALTER TABLE public.candidates ADD COLUMN IF NOT EXISTS education TEXT;
ALTER TABLE public.candidates ADD COLUMN IF NOT EXISTS experience_years INTEGER;

COMMIT;
