-- T2704: Prompt v2 (Agenta vendor-in)
--
-- Adds:
--   * prompt_versions    - canonical prompt registry with versioning + traffic split
--   * prompt_metrics    - per-version evaluation metrics (LLM-as-judge 4 dimensions)
--   * prompt_evaluations- raw evaluation runs (gold-standard cases)
--
-- Design notes:
--   * Multi-tenant: tenant_id is the primary isolation boundary
--   * name + agent  -> logical prompt identity
--   * version       -> monotonically increasing integer per (tenant, name)
--   * traffic_pct   -> 0..100 (sum of active versions per (tenant, name, agent) must equal 100)
--   * status        -> draft / active / retired
--   * content       -> the prompt template body (system+user joined)
--   * variables     -> JSON list of expected input variable names
--   * tags          -> JSON list of free-form tags (e.g. "experiment-2026Q3")
--
-- RLS:
--   * service_role has full access (admin / evaluation workers)
--   * authenticated: users see only their own tenant's prompts
--   * prompt_metrics is append-only via service_role

BEGIN;

-- ----------------------------------------------------------------------
-- 0. Required extensions
-- ----------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ----------------------------------------------------------------------
-- 1. prompt_versions
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.prompt_versions (
  id              uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id       uuid        NOT NULL,
  name            text        NOT NULL,
  agent           text        NOT NULL DEFAULT 'default',
  version         int         NOT NULL,
  content         text        NOT NULL,
  description     text,
  variables       jsonb       NOT NULL DEFAULT '[]'::jsonb,
  tags            jsonb       NOT NULL DEFAULT '[]'::jsonb,
  traffic_pct     int         NOT NULL DEFAULT 100
                              CHECK (traffic_pct >= 0 AND traffic_pct <= 100),
  status          text        NOT NULL DEFAULT 'draft'
                              CHECK (status IN ('draft','active','retired')),
  parent_version  int,
  created_by      text        NOT NULL DEFAULT 'system',
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  retired_at      timestamptz,
  metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (tenant_id, name, agent, version)
);

CREATE INDEX IF NOT EXISTS idx_prompt_versions_active
  ON public.prompt_versions (tenant_id, name, agent)
  WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_prompt_versions_tenant
  ON public.prompt_versions (tenant_id, created_at DESC);

-- ----------------------------------------------------------------------
-- 2. prompt_metrics
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.prompt_metrics (
  id              uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id       uuid        NOT NULL,
  prompt_id       uuid        NOT NULL REFERENCES public.prompt_versions(id) ON DELETE CASCADE,
  version         int         NOT NULL,
  metric_name     text        NOT NULL,   -- 'accuracy' | 'fluency' | 'safety' | 'bias' | 'overall'
  value           real        NOT NULL
                              CHECK (value >= 0 AND value <= 1),
  sample_size     int         NOT NULL DEFAULT 0
                              CHECK (sample_size >= 0),
  computed_at     timestamptz NOT NULL DEFAULT now(),
  metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_prompt_metrics_prompt
  ON public.prompt_metrics (prompt_id, metric_name, computed_at DESC);

-- ----------------------------------------------------------------------
-- 3. prompt_evaluations
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.prompt_evaluations (
  id              uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id       uuid        NOT NULL,
  prompt_id       uuid        NOT NULL REFERENCES public.prompt_versions(id) ON DELETE CASCADE,
  version         int         NOT NULL,
  case_id         text        NOT NULL,
  input           text        NOT NULL,
  output          text        NOT NULL,
  expected        text,
  accuracy_score  real,
  fluency_score   real,
  safety_score    real,
  bias_score      real,
  overall_score   real,
  judge_model     text        NOT NULL DEFAULT 'gpt-4o',
  judge_notes     text,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_prompt_evaluations_prompt
  ON public.prompt_evaluations (prompt_id, created_at DESC);

-- ----------------------------------------------------------------------
-- 4. Row Level Security
-- ----------------------------------------------------------------------
ALTER TABLE public.prompt_versions    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prompt_metrics     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prompt_evaluations ENABLE ROW LEVEL SECURITY;

-- service_role bypass
DROP POLICY IF EXISTS prompt_versions_service ON public.prompt_versions;
CREATE POLICY prompt_versions_service ON public.prompt_versions
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS prompt_metrics_service ON public.prompt_metrics;
CREATE POLICY prompt_metrics_service ON public.prompt_metrics
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS prompt_evaluations_service ON public.prompt_evaluations;
CREATE POLICY prompt_evaluations_service ON public.prompt_evaluations
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- tenant-scoped read/write for authenticated users
DROP POLICY IF EXISTS prompt_versions_tenant ON public.prompt_versions;
CREATE POLICY prompt_versions_tenant ON public.prompt_versions
  FOR ALL TO authenticated
  USING (tenant_id::text = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS prompt_metrics_tenant ON public.prompt_metrics;
CREATE POLICY prompt_metrics_tenant ON public.prompt_metrics
  FOR ALL TO authenticated
  USING (tenant_id::text = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS prompt_evaluations_tenant ON public.prompt_evaluations;
CREATE POLICY prompt_evaluations_tenant ON public.prompt_evaluations
  FOR ALL TO authenticated
  USING (tenant_id::text = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));

-- ----------------------------------------------------------------------
-- 5. updated_at trigger
-- ----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.tg_set_updated_at_prompt()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prompt_versions_updated ON public.prompt_versions;
CREATE TRIGGER trg_prompt_versions_updated
  BEFORE UPDATE ON public.prompt_versions
  FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at_prompt();

COMMIT;