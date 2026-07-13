-- T2702: Agent 统一记忆库 v2 (Mem0 vendor-in)
--
-- Adds:
--   * memories_v2         - the canonical memory store (per user / per tenant)
--   * memory_links_v2     - graph-style relations between memories
--   * memory_access_v2    - audit trail for GDPR / data subject requests
--   * memory_decay_jobs   - background job tracking for periodic decay
--
-- Design notes:
--   * Multi-tenant: tenant_id is the primary isolation boundary
--   * type: fact / preference / event / summary / task — drives UI grouping
--   * confidence: 0..1, source_agent: which agent wrote this row
--   * embedding: pgvector mirror (1024-dim BGE) — primary ANN can also be Qdrant
--   * decay_score: 0..1, periodically multiplied (memories fade when not accessed)
--   * Links model: a-b relations (e.g. "fact about Alice" -- "preference of Bob")
--
-- RLS:
--   * service_role has full access (admin / background workers)
--   * authenticated: users see only their own memories (user_id = auth.uid())
--   * employers: see only their tenant's memories (tenant_id derived from JWT)

BEGIN;

-- ----------------------------------------------------------------------
-- 0. Required extensions
-- ----------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgvector";

-- ----------------------------------------------------------------------
-- 1. memories_v2
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.memories_v2 (
  id              uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id       uuid        NOT NULL,
  user_id         uuid        NOT NULL,
  content         text        NOT NULL,
  summary         text,
  embedding       vector(1024),
  source_agent    text        NOT NULL,
  type            text        NOT NULL DEFAULT 'fact'
                              CHECK (type IN ('fact','preference','event','summary','task','episodic')),
  confidence      real        NOT NULL DEFAULT 1.0
                              CHECK (confidence >= 0 AND confidence <= 1),
  decay_score     real        NOT NULL DEFAULT 1.0
                              CHECK (decay_score >= 0 AND decay_score <= 1),
  access_count    int         NOT NULL DEFAULT 0,
  last_accessed   timestamptz,
  metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,
  is_archived     boolean     NOT NULL DEFAULT false,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memories_v2_tenant_user
  ON public.memories_v2 (tenant_id, user_id)
  WHERE is_archived = false;

CREATE INDEX IF NOT EXISTS idx_memories_v2_user_created
  ON public.memories_v2 (user_id, created_at DESC)
  WHERE is_archived = false;

CREATE INDEX IF NOT EXISTS idx_memories_v2_agent
  ON public.memories_v2 (source_agent, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_memories_v2_type
  ON public.memories_v2 (user_id, type)
  WHERE is_archived = false;

-- pgvector HNSW index for embedding similarity
CREATE INDEX IF NOT EXISTS idx_memories_v2_embedding_hnsw
  ON public.memories_v2 USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- ----------------------------------------------------------------------
-- 2. memory_links_v2 (graph relations)
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.memory_links_v2 (
  id              uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  memory_id_a     uuid        NOT NULL REFERENCES public.memories_v2(id) ON DELETE CASCADE,
  memory_id_b     uuid        NOT NULL REFERENCES public.memories_v2(id) ON DELETE CASCADE,
  relation        text        NOT NULL
                              CHECK (relation IN ('related','follows','contradicts','supports','derived_from','references')),
  weight          real        NOT NULL DEFAULT 1.0,
  metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (memory_id_a, memory_id_b, relation)
);

CREATE INDEX IF NOT EXISTS idx_memory_links_v2_a
  ON public.memory_links_v2 (memory_id_a);

CREATE INDEX IF NOT EXISTS idx_memory_links_v2_b
  ON public.memory_links_v2 (memory_id_b);

-- ----------------------------------------------------------------------
-- 3. memory_access_v2 (audit trail for GDPR DSR)
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.memory_access_v2 (
  id              uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  memory_id       uuid        NOT NULL REFERENCES public.memories_v2(id) ON DELETE CASCADE,
  user_id         uuid        NOT NULL,
  action          text        NOT NULL
                              CHECK (action IN ('read','write','update','delete','forget','export')),
  actor_id        uuid,
  actor_kind      text        NOT NULL DEFAULT 'user'
                              CHECK (actor_kind IN ('user','agent','admin','system','gdpr_job')),
  reason          text,
  payload         jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memory_access_v2_memory
  ON public.memory_access_v2 (memory_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_access_v2_user
  ON public.memory_access_v2 (user_id, created_at DESC);

-- ----------------------------------------------------------------------
-- 4. memory_decay_jobs (background job tracking)
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.memory_decay_jobs (
  id              uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id       uuid,
  job_type        text        NOT NULL
                              CHECK (job_type IN ('decay','reindex','forget_user','export_user','consolidate')),
  status          text        NOT NULL DEFAULT 'pending'
                              CHECK (status IN ('pending','running','completed','failed')),
  affected_rows   int         NOT NULL DEFAULT 0,
  error           text,
  started_at      timestamptz,
  completed_at    timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memory_decay_jobs_status
  ON public.memory_decay_jobs (status, created_at DESC);

-- ----------------------------------------------------------------------
-- 5. updated_at trigger
-- ----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.memories_v2_set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_memories_v2_updated_at ON public.memories_v2;
CREATE TRIGGER trg_memories_v2_updated_at
  BEFORE UPDATE ON public.memories_v2
  FOR EACH ROW
  EXECUTE FUNCTION public.memories_v2_set_updated_at();

-- ----------------------------------------------------------------------
-- 6. RLS — tenant isolation
-- ----------------------------------------------------------------------
ALTER TABLE public.memories_v2      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_links_v2  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_access_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_decay_jobs ENABLE ROW LEVEL SECURITY;

-- helper: tenant_id from JWT
CREATE OR REPLACE FUNCTION memory_current_tenant()
RETURNS uuid
LANGUAGE sql STABLE
AS $$
  SELECT NULLIF(
    coalesce(
      current_setting('request.jwt.claims', true)::jsonb -> 'app_metadata' ->> 'tenant_id',
      current_setting('app.tenant_id', true)
    ),
    ''
  )::uuid;
$$;

-- helper: user_id from JWT
CREATE OR REPLACE FUNCTION memory_current_user()
RETURNS uuid
LANGUAGE sql STABLE
AS $$
  SELECT NULLIF(
    coalesce(
      current_setting('request.jwt.claims', true)::jsonb ->> 'sub',
      current_setting('app.user_id', true)
    ),
    ''
  )::uuid;
$$;

-- Service role: full access
DROP POLICY IF EXISTS memory_service_role_all_memories ON public.memories_v2;
CREATE POLICY memory_service_role_all_memories ON public.memories_v2
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS memory_service_role_all_links ON public.memory_links_v2;
CREATE POLICY memory_service_role_all_links ON public.memory_links_v2
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS memory_service_role_all_access ON public.memory_access_v2;
CREATE POLICY memory_service_role_all_access ON public.memory_access_v2
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS memory_service_role_all_jobs ON public.memory_decay_jobs;
CREATE POLICY memory_service_role_all_jobs ON public.memory_decay_jobs
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Authenticated users: see their own memories
DROP POLICY IF EXISTS memory_user_r_memories ON public.memories_v2;
CREATE POLICY memory_user_r_memories ON public.memories_v2
  FOR SELECT TO authenticated
  USING (user_id = memory_current_user());

DROP POLICY IF EXISTS memory_user_w_memories ON public.memories_v2;
CREATE POLICY memory_user_w_memories ON public.memories_v2
  FOR INSERT TO authenticated
  WITH CHECK (user_id = memory_current_user());

DROP POLICY IF EXISTS memory_user_u_memories ON public.memories_v2;
CREATE POLICY memory_user_u_memories ON public.memories_v2
  FOR UPDATE TO authenticated
  USING (user_id = memory_current_user())
  WITH CHECK (user_id = memory_current_user());

DROP POLICY IF EXISTS memory_user_d_memories ON public.memories_v2;
CREATE POLICY memory_user_d_memories ON public.memories_v2
  FOR DELETE TO authenticated
  USING (user_id = memory_current_user());

-- Authenticated users: links to their own memories
DROP POLICY IF EXISTS memory_user_r_links ON public.memory_links_v2;
CREATE POLICY memory_user_r_links ON public.memory_links_v2
  FOR SELECT TO authenticated
  USING (
    EXISTS (SELECT 1 FROM public.memories_v2 m
            WHERE m.id = memory_links_v2.memory_id_a
              AND m.user_id = memory_current_user())
  );

-- Authenticated users: read their own access log
DROP POLICY IF EXISTS memory_user_r_access ON public.memory_access_v2;
CREATE POLICY memory_user_r_access ON public.memory_access_v2
  FOR SELECT TO authenticated
  USING (user_id = memory_current_user());

-- Authenticated users: read jobs in their tenant
DROP POLICY IF EXISTS memory_tenant_r_jobs ON public.memory_decay_jobs;
CREATE POLICY memory_tenant_r_jobs ON public.memory_decay_jobs
  FOR SELECT TO authenticated
  USING (
    tenant_id IS NULL OR tenant_id = memory_current_tenant()
  );

-- Realtime
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime' AND tablename = 'memories_v2'
  ) THEN
    EXECUTE 'ALTER PUBLICATION supabase_realtime ADD TABLE public.memories_v2';
  END IF;
END$$;

COMMIT;
