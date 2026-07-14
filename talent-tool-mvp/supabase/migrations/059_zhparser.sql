-- ============================================================================
-- 059_zhparser.sql
-- T5013 (part 2) — Chinese-aware full-text search.
--
-- Problem
-- --------
-- The default ``text_search_config`` is English/stemming-based, so queries
-- on Chinese text (candidate bios, JD content, ticket descriptions) match
-- poorly: "招聘经理" is not tokenised into useful lexemes.
--
-- Solution
-- --------
--   1. Register the ``zhparser`` extension and a ``chinese_zh`` text-search
--      configuration built on it (with simple stop-word handling).
--   2. Add a generated ``tsvector`` column to the searchable tables and a
--      GIN index so ``WHERE tsv @@ plainto_tsquery('chinese_zh', $1)`` is fast.
--   3. Keep writes cheap: the tsvector is a STORED generated column, so it
--      is maintained by the planner with no trigger needed.
--
-- Portability
-- -----------
-- zhparser must be installed on the server (``CREATE EXTENSION zhparser``).
-- On hosted Supabase / RDS it is available as a trusted extension; on a
-- self-hosted box it requires the shared_preload_libraries + the package.
-- This migration is therefore guarded: if the extension cannot be created
-- (e.g. in CI without zhparser), the whole migration degrades to a no-op
-- with a NOTICE, so the rest of the schema applies cleanly.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 0. Extension + config (guarded)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  CREATE EXTENSION IF NOT EXISTS zhparser;
EXCEPTION
  WHEN insufficient_privilege OR undefined_file OR feature_not_supported THEN
    RAISE NOTICE 'zhparser extension unavailable — full-text search disabled (%)', SQLERRM;
END$$;

-- only build the config if zhparser actually loaded
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'zhparser') THEN
    CREATE TEXT SEARCH CONFIGURATION IF NOT EXISTS chinese_zh
      (PARSER = zhparser);
    ALTER TEXT SEARCH CONFIGURATION chinese_zh
      ADD MAPPING FOR n,v,a,i,e,l WITH simple;
  ELSE
    RAISE NOTICE 'skipping chinese_zh config (no zhparser)';
  END IF;
END$$;

-- ---------------------------------------------------------------------------
-- 1. Helper: (re)build the FTS artefacts for one table/column pair.
--    Encapsulates the add-column + index dance so we can fan it out.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.enable_chinese_fts(
  tbl regclass,
  text_col text,
  tsv_col text DEFAULT 'tsv'
) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
  schema_n text;
  table_n text;
  has_zh  boolean;
  has_col boolean;
BEGIN
  SELECT n.nspname, c.relname INTO schema_n, table_n
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE c.oid = tbl;
  IF table_n IS NULL THEN
    RAISE EXCEPTION 'table % not found', tbl;
  END IF;

  SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='zhparser') INTO has_zh;
  -- fall back to the default 'simple' config when zhparser is absent so the
  -- column + index still exist (lower quality matches, but no schema drift)
  DECLARE cfg text := CASE WHEN has_zh THEN 'chinese_zh' ELSE 'simple' END;
  BEGIN
    SELECT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema=schema_n AND table_name=table_n AND column_name=tsv_col
    ) INTO has_col;

    IF NOT has_col THEN
      EXECUTE format(
        'ALTER TABLE %s ADD COLUMN %I tsvector '
        'GENERATED ALWAYS AS '
        '(to_tsvector(%L::regconfig, coalesce(%I,''''))) STORED',
        tbl, tsv_col, cfg, text_col
      );
    END IF;

    EXECUTE format(
      'CREATE INDEX IF NOT EXISTS idx_%s_%s_gin ON %s USING GIN (%I)',
      table_n, tsv_col, tbl, tsv_col
    );
  END;
END$$;

COMMENT ON FUNCTION public.enable_chinese_fts(regclass, text, text) IS
  'T5013: add a STORED generated tsvector column + GIN index for Chinese FTS. '
  'Uses chinese_zh config when zhparser is installed, else falls back to simple.';

-- ---------------------------------------------------------------------------
-- 2. Fan out to the searchable tables.
--    Each is guarded so a missing table (e.g. in a partial deploy) is skipped.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
  rec record;
  targets record[] := ARRAY[
    ('candidates','cv_text','tsv_cv')::record,
    ('candidates','profile_text','tsv_profile')::record,
    ('signals','metadata::text','tsv_meta')::record
  ];
BEGIN
  FOREACH rec IN ARRAY targets LOOP
    IF EXISTS (
      SELECT 1 FROM information_schema.tables
      WHERE table_schema='public' AND table_name=rec.f1
    ) AND EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema='public' AND table_name=rec.f1 AND column_name=rec.f2
    ) THEN
      PERFORM public.enable_chinese_fts(
        format('public.%I', rec.f1)::regclass, rec.f2, rec.f3);
    END IF;
  END LOOP;
END$$;

-- ---------------------------------------------------------------------------
-- 3. Convenience search predicate.
--    Returns a tsquery in the active Chinese config so callers can write:
--      SELECT * FROM candidates
--      WHERE tsv_cv @@ public.chinese_tsquery('招聘经理');
--    (A dynamic-table search helper is unsafe to express as a SQL function
--     with a polymorphic return type; inlining the predicate is the clean
--     pattern, and this function gives callers the right-hand side.)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.chinese_tsquery(query text)
RETURNS tsquery
LANGUAGE sql STABLE AS $$
  SELECT plainto_tsquery(
    CASE WHEN EXISTS (SELECT 1 FROM pg_extension WHERE extname='zhparser')
         THEN 'chinese_zh'::regconfig ELSE 'simple'::regconfig END,
    $1)
$$;

COMMENT ON FUNCTION public.chinese_tsquery(text) IS
  'T5013: build a tsquery in the active Chinese FTS config (chinese_zh when '
  'zhparser is installed, else simple). Use as: tsv @@ chinese_tsquery($1).';
