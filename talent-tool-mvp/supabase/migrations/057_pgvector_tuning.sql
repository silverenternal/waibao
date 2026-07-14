-- ============================================================================
-- 057_pgvector_tuning.sql
-- T5012 (part 1) — unify all vector indexes on HNSW + set ef_search=200.
--
-- Why
-- ---
-- pgvector offers two ANN index types:
--   * IVFFlat — build-fast, query-OK, but quality degrades as data grows and
--               it must be rebuilt after large inserts to stay accurate;
--   * HNSW    — build-slower, but recall@k is materially higher and it does
--               not need rebuilding on data growth.
--
-- We standardised most tables on HNSW already (migrations 001/048/049), but
-- ``company_policies`` (migration 005) still uses IVFFlat.  This migration:
--   1. replaces the lone IVFFlat index with HNSW so the whole fleet is
--      homogeneous (one tuning surface, one set of operator expectations),
--   2. sets the runtime search-width GUC ``hnsw.ef_search = 200`` as the
--      session default (recall ~0.99 at our corpus sizes; tunable per-query
--      via SET LOCAL),
--   3. tunes HNSW build parameters (m=16, ef_construction=64) — the pgvector
--      recommended defaults for a balance of build cost and recall,
--   4. records the policy in a comment so the next engineer knows where to
--      tune.
--
-- CONCURRENTLY: index (re)builds must not block writes, so each is issued
-- with CREATE INDEX CONCURRENTLY / reindex-equivalent.  This file is NOT
-- wrapped in BEGIN/COMMIT.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 0. Ensure the vector extension is present (idempotent).
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- 1. Replace the company_policies IVFFlat index with HNSW.
--    Drop the legacy index first, then build HNSW concurrently.
-- ---------------------------------------------------------------------------
DROP INDEX IF EXISTS public.company_policies_embedding_idx;
-- (the original name in 005 was ``company_policies_embedding_idx``; if a
--  different name was used, the IF EXISTS guard makes this safe.)

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_company_policies_embedding_hnsw
    ON public.company_policies
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ---------------------------------------------------------------------------
-- 2. Re-affirm HNSW on the other embedding columns with explicit build params.
--    CREATE INDEX CONCURRENTLY IF NOT EXISTS is a no-op if the index already
--    exists, so existing HNSW indexes (001/048/049) keep their original build
--    parameters — we only add new ones for any column that lacks HNSW.
-- ---------------------------------------------------------------------------

-- candidates (1536-d, semantic candidate search)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_candidates_embedding_hnsw
    ON public.candidates
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- roles (1536-d, role-side semantic match)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_roles_embedding_hnsw
    ON public.roles
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- rag chunks (1024-d, knowledge retrieval)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_rag_chunks_embedding_hnsw
    ON public.rag_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- agent memories v2 (1024-d, Mem0-style recall)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_memories_v2_embedding_hnsw_tuned
    ON public.memories_v2
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ---------------------------------------------------------------------------
-- 3. Session-default ef_search = 200.
--    ALTER DATABASE ... SET makes it the default for every new connection,
--    so the backend pool inherits it without per-request SET.  Per-query
--    override is still possible via ``SET LOCAL hnsw.ef_search``.
-- ---------------------------------------------------------------------------
-- ALTER DATABASE requires a literal name, so we resolve it dynamically
-- inside a DO block (portable across dev/stage/prod database names).
DO $$
BEGIN
  EXECUTE format('ALTER DATABASE %I SET hnsw.ef_search = 200',
                 current_database());
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'could not ALTER DATABASE ef_search: %', SQLERRM;
END$$;

-- (belt-and-suspenders: also expose a helper to set it inside a tx)
CREATE OR REPLACE FUNCTION public.set_vector_search_width(ef integer DEFAULT 200)
RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
  -- clamp to pgvector's valid range [1, 1000]
  IF ef < 1 OR ef > 1000 THEN
    RAISE EXCEPTION 'ef_search out of range [1,1000]: %', ef
      USING ERRCODE = '22023';
  END IF;
  PERFORM set_config('hnsw.ef_search', ef::text, true);  -- true = local to tx
END$$;

COMMENT ON FUNCTION public.set_vector_search_width(integer) IS
  'T5012: set hnsw.ef_search for the current transaction (default 200). '
  'Higher = better recall, slower query.';

-- ---------------------------------------------------------------------------
-- 4. Documentation anchor.
-- ---------------------------------------------------------------------------
COMMENT ON INDEX public.idx_company_policies_embedding_hnsw IS
  'T5012: HNSW vector index (was IVFFlat). m=16, ef_construction=64. '
  'ef_search default=200 (see ALTER DATABASE hnsw.ef_search).';
