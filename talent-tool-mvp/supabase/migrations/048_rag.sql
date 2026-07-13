-- T2701: 完整 RAG (LlamaIndex + Qdrant)
--
-- Adds:
--   * rag_collections          - tenant-scoped RAG index definitions
--   * rag_documents            - uploaded document registry
--   * rag_chunks               - split + embedded chunks (pgvector mirror of Qdrant)
--   * rag_ingestion_jobs       - async ingestion pipeline tracking
--   * rag_query_logs           - retrieval/answer observability
--
-- RLS:
--   * tenant_id derived from auth.jwt() -> app_metadata.tenant_id (defense in depth)
--   * service_role can read/write (admin / ingestion)
--   * employer_admin/employer_user only see their tenant
--
-- pgvector mirror:
--   * 1024-dim default (BGE) for cost-effective search via HNSW
--   * Qdrant is the primary ANN store; pgvector is the safety-net / fallback

BEGIN;

-- ----------------------------------------------------------------------
-- 0. Required extensions
-- ----------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgvector";

-- ----------------------------------------------------------------------
-- 1. Collections (a tenant can own many RAG indices)
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.rag_collections (
  id              uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id       uuid        NOT NULL,
  name            text        NOT NULL,
  description     text,
  embedding_model text        NOT NULL DEFAULT 'bge-large-en-v1.5',
  embedding_dim   int         NOT NULL DEFAULT 1024,
  qdrant_collection text     NOT NULL,
  chunk_size      int         NOT NULL DEFAULT 512,
  chunk_overlap   int         NOT NULL DEFAULT 50,
  reranker_model  text        NOT NULL DEFAULT 'bge-reranker-large',
  metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,
  is_active       boolean     NOT NULL DEFAULT true,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);

CREATE INDEX IF NOT EXISTS idx_rag_collections_tenant
  ON public.rag_collections (tenant_id)
  WHERE is_active = true;

-- ----------------------------------------------------------------------
-- 2. Documents (uploaded files)
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.rag_documents (
  id              uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id       uuid        NOT NULL,
  collection_id   uuid        NOT NULL REFERENCES public.rag_collections(id) ON DELETE CASCADE,
  name            text        NOT NULL,
  display_name    text        NOT NULL,
  source          text        NOT NULL,        -- e.g. "upload", "url", "gdrive", "notion"
  mime_type       text,
  size_bytes      bigint      NOT NULL DEFAULT 0,
  storage_path    text,                        -- supabase storage path or external URL
  status          text        NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending', 'parsing', 'chunking',
                                                  'embedding', 'indexed', 'failed', 'deleted')),
  error_message   text,
  total_chunks    int         NOT NULL DEFAULT 0,
  total_tokens    int         NOT NULL DEFAULT 0,
  language        text,
  metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,
  uploaded_by     uuid,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rag_documents_tenant
  ON public.rag_documents (tenant_id);
CREATE INDEX IF NOT EXISTS idx_rag_documents_collection
  ON public.rag_documents (collection_id);
CREATE INDEX IF NOT EXISTS idx_rag_documents_status
  ON public.rag_documents (status)
  WHERE status NOT IN ('indexed', 'deleted', 'failed');

-- ----------------------------------------------------------------------
-- 3. Chunks (with pgvector mirror embedding)
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.rag_chunks (
  id              uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id     uuid        NOT NULL REFERENCES public.rag_documents(id) ON DELETE CASCADE,
  tenant_id       uuid        NOT NULL,
  collection_id   uuid        NOT NULL REFERENCES public.rag_collections(id) ON DELETE CASCADE,
  position        int         NOT NULL,
  content         text        NOT NULL,
  content_tsv     tsvector,
  token_count     int         NOT NULL DEFAULT 0,
  embedding       vector(1024),
  metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, position)
);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_document
  ON public.rag_chunks (document_id, position);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_tenant
  ON public.rag_chunks (tenant_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_collection
  ON public.rag_chunks (collection_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_tsv
  ON public.rag_chunks USING gin (content_tsv);

-- pgvector HNSW (cosine) — fallback / hybrid search
CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding
  ON public.rag_chunks
  USING hnsw (embedding vector_cosine_ops);

-- Auto-maintain tsvector for BM25-style keyword search
CREATE OR REPLACE FUNCTION rag_chunks_tsv_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.content_tsv := to_tsvector('english', coalesce(NEW.content, ''));
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_rag_chunks_tsv ON public.rag_chunks;
CREATE TRIGGER trg_rag_chunks_tsv
  BEFORE INSERT OR UPDATE OF content
  ON public.rag_chunks
  FOR EACH ROW EXECUTE FUNCTION rag_chunks_tsv_update();

-- updated_at trigger for collections + documents
CREATE OR REPLACE FUNCTION touch_updated_at_rag()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_rag_collections_touch ON public.rag_collections;
CREATE TRIGGER trg_rag_collections_touch
  BEFORE UPDATE ON public.rag_collections
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at_rag();

DROP TRIGGER IF EXISTS trg_rag_documents_touch ON public.rag_documents;
CREATE TRIGGER trg_rag_documents_touch
  BEFORE UPDATE ON public.rag_documents
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at_rag();

-- ----------------------------------------------------------------------
-- 4. Ingestion jobs
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.rag_ingestion_jobs (
  id              uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id       uuid        NOT NULL,
  document_id     uuid        NOT NULL REFERENCES public.rag_documents(id) ON DELETE CASCADE,
  status          text        NOT NULL DEFAULT 'queued'
                                CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
  started_at      timestamptz,
  finished_at     timestamptz,
  error_message   text,
  stats           jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rag_jobs_tenant_status
  ON public.rag_ingestion_jobs (tenant_id, status);

-- ----------------------------------------------------------------------
-- 5. Query logs (observability + cost tracking)
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.rag_query_logs (
  id                uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id         uuid        NOT NULL,
  collection_id     uuid        REFERENCES public.rag_collections(id) ON DELETE SET NULL,
  query             text        NOT NULL,
  retrieved_ids     uuid[]      NOT NULL DEFAULT ARRAY[]::uuid[],
  citations         jsonb       NOT NULL DEFAULT '[]'::jsonb,
  answer            text,
  retrieval_ms      int         NOT NULL DEFAULT 0,
  generation_ms     int         NOT NULL DEFAULT 0,
  total_tokens      int         NOT NULL DEFAULT 0,
  model             text,
  user_id           uuid,
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rag_query_logs_tenant_time
  ON public.rag_query_logs (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rag_query_logs_collection
  ON public.rag_query_logs (collection_id);

-- ----------------------------------------------------------------------
-- 6. RLS — tenant isolation
-- ----------------------------------------------------------------------
ALTER TABLE public.rag_collections   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rag_documents     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rag_chunks        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rag_ingestion_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rag_query_logs    ENABLE ROW LEVEL SECURITY;

-- helper to read tenant_id from JWT
CREATE OR REPLACE FUNCTION rag_current_tenant()
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

-- Service role: full access
DROP POLICY IF EXISTS rag_service_role_all_collections ON public.rag_collections;
CREATE POLICY rag_service_role_all_collections ON public.rag_collections
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS rag_service_role_all_documents ON public.rag_documents;
CREATE POLICY rag_service_role_all_documents ON public.rag_documents
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS rag_service_role_all_chunks ON public.rag_chunks;
CREATE POLICY rag_service_role_all_chunks ON public.rag_chunks
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS rag_service_role_all_jobs ON public.rag_ingestion_jobs;
CREATE POLICY rag_service_role_all_jobs ON public.rag_ingestion_jobs
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS rag_service_role_all_logs ON public.rag_query_logs;
CREATE POLICY rag_service_role_all_logs ON public.rag_query_logs
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Tenant-scoped: employer_admin + employer_user (read+write documents within their tenant)
DROP POLICY IF EXISTS rag_tenant_rw_collections ON public.rag_collections;
CREATE POLICY rag_tenant_rw_collections ON public.rag_collections
  FOR ALL TO authenticated
  USING (tenant_id = rag_current_tenant())
  WITH CHECK (tenant_id = rag_current_tenant());

DROP POLICY IF EXISTS rag_tenant_rw_documents ON public.rag_documents;
CREATE POLICY rag_tenant_rw_documents ON public.rag_documents
  FOR ALL TO authenticated
  USING (tenant_id = rag_current_tenant())
  WITH CHECK (tenant_id = rag_current_tenant());

DROP POLICY IF EXISTS rag_tenant_rw_chunks ON public.rag_chunks;
CREATE POLICY rag_tenant_rw_chunks ON public.rag_chunks
  FOR ALL TO authenticated
  USING (tenant_id = rag_current_tenant())
  WITH CHECK (tenant_id = rag_current_tenant());

DROP POLICY IF EXISTS rag_tenant_rw_jobs ON public.rag_ingestion_jobs;
CREATE POLICY rag_tenant_rw_jobs ON public.rag_ingestion_jobs
  FOR ALL TO authenticated
  USING (tenant_id = rag_current_tenant())
  WITH CHECK (tenant_id = rag_current_tenant());

DROP POLICY IF EXISTS rag_tenant_r_logs ON public.rag_query_logs;
CREATE POLICY rag_tenant_r_logs ON public.rag_query_logs
  FOR SELECT TO authenticated
  USING (tenant_id = rag_current_tenant());

DROP POLICY IF EXISTS rag_tenant_w_logs ON public.rag_query_logs;
CREATE POLICY rag_tenant_w_logs ON public.rag_query_logs
  FOR INSERT TO authenticated
  WITH CHECK (tenant_id = rag_current_tenant());

-- Realtime channels (chat-with-docs)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime' AND tablename = 'rag_query_logs'
  ) THEN
    EXECUTE 'ALTER PUBLICATION supabase_realtime ADD TABLE public.rag_query_logs';
  END IF;
END$$;

COMMIT;
