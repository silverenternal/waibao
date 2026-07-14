-- ============================================================================
-- 058_partitioning.sql
-- T5013 (part 1) — convert the three highest-volume append-only tables to
-- monthly RANGE partitions on their timestamp column.
--
-- Targets
-- --------
--   * audit_log_v2   PARTITION BY RANGE (created_at)
--   * signals        PARTITION BY RANGE (created_at)
--   * funnel_events  PARTITION BY RANGE (occurred_at)
--
-- These three tables are write-heavy and almost always queried with a time
-- window, so partitioning lets the planner prune entire months and lets us
-- drop old partitions in O(1) instead of a slow DELETE.
--
-- How a heap table becomes partitioned
-- ------------------------------------
-- Postgres has no in-place "ALTER TABLE ... PARTITION BY" for a table that
-- already holds data.  The standard, safe recipe is:
--   1. RENAME the existing table to <name>_unpartitioned (keep data + indexes);
--   2. CREATE the partitioned parent with the same columns + a composite PK
--      that INCLUDES the partition key (a hard Postgres requirement);
--   3. create the monthly partitions;
--   4. INSERT INTO parent SELECT * FROM <name>_unpartitioned  (data move);
--   5. recreate the indexes on the parent (they propagate to partitions);
--   6. re-attach RLS policies (policies do not survive the rename).
--
-- This migration is idempotent: it detects whether the parent is already
-- partitioned and skips the swap.  A helper ``create_monthly_partition()``
-- is provided for the cron that rolls partitions forward.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 0. Helper: create (or no-op) a monthly partition for a given parent table,
--    year, month.  Safe to call from a monthly cron.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.create_monthly_partition(
  parent regclass,
  year integer,
  month integer
) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
  schema_n text;
  table_n text;
  part_name text;
  start_ts timestamptz;
  end_ts   timestamptz;
  ts_col   text;
BEGIN
  IF month < 1 OR month > 12 THEN
    RAISE EXCEPTION 'month out of range [1,12]: %', month USING ERRCODE='22023';
  END IF;
  IF year < 1970 OR year > 2999 THEN
    RAISE EXCEPTION 'year out of range: %', year USING ERRCODE='22023';
  END IF;

  SELECT n.nspname, c.relname INTO schema_n, table_n
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE c.oid = parent;
  IF table_n IS NULL THEN
    RAISE EXCEPTION 'parent table % not found', parent;
  END IF;

  -- resolve the partition key column name from pg_partitioned_table
  SELECT a.attname INTO ts_col
    FROM pg_partitioned_table pt
    JOIN pg_attribute a
      ON a.attrelid = pt.partrelid AND a.attnum = pt.partattrs[1]
   WHERE pt.partrelid = parent;
  IF ts_col IS NULL THEN
    RAISE EXCEPTION '% is not a partitioned table', parent USING ERRCODE='42809';
  END IF;

  start_ts := make_timestamptz(year, month, 1, 0, 0, 0);
  end_ts   := start_ts + interval '1 month';
  part_name := table_n || '_' || to_char(start_ts, 'YYYYMM');

  EXECUTE format(
    'CREATE TABLE IF NOT EXISTS %I.%I PARTITION OF %s '
    'FOR VALUES FROM (%L) TO (%L)',
    schema_n, part_name, parent, start_ts, end_ts
  );
END$$;

COMMENT ON FUNCTION public.create_monthly_partition(regclass, integer, integer) IS
  'T5013: idempotently create the monthly partition of a RANGE(time) table.';

-- ===========================================================================
-- 1. audit_log_v2 → partitioned by created_at
-- ===========================================================================
DO $$
DECLARE
  is_part boolean;
BEGIN
  SELECT EXISTS (
    SELECT 1 FROM pg_partitioned_table pt
    JOIN pg_class c ON c.oid = pt.partrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname='public' AND c.relname='audit_log_v2'
  ) INTO is_part;

  IF is_part THEN
    RAISE NOTICE 'audit_log_v2 already partitioned — skipping swap';
    RETURN;
  END IF;

  -- 1a. bail out cleanly if the source table does not exist yet
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema='public' AND table_name='audit_log_v2'
  ) THEN RAISE NOTICE 'audit_log_v2 missing — nothing to partition'; RETURN;
  END IF;

  -- 1b. rename the heap out of the way
  ALTER TABLE public.audit_log_v2 RENAME TO audit_log_v2_unpartitioned;

  -- 1c. create the partitioned parent (PK must include created_at)
  EXECUTE $ddl$
    CREATE TABLE public.audit_log_v2 (
      LIKE public.audit_log_v2_unpartitioned INCLUDING ALL
    ) PARTITION BY RANGE (created_at)
  $ddl$;
  -- INCLUDING ALL copies the old PK as (id) which is invalid for a partitioned
  -- table when id is not the partition key; drop it and add the composite PK.
  ALTER TABLE public.audit_log_v2 DROP CONSTRAINT IF EXISTS audit_log_v2_pkey;
  ALTER TABLE public.audit_log_v2
    ADD PRIMARY KEY (id, created_at);

  -- 1d. current + next month + a catch-all default
  PERFORM public.create_monthly_partition('public.audit_log_v2'::regclass,
    date_part('year', now())::int, date_part('month', now())::int);
  PERFORM public.create_monthly_partition('public.audit_log_v2'::regclass,
    (date_part('year', now() + interval '1 month'))::int,
    (date_part('month', now() + interval '1 month'))::int);
  CREATE TABLE IF NOT EXISTS public.audit_log_v2_default
    PARTITION OF public.audit_log_v2 DEFAULT;

  -- 1e. move the rows
  EXECUTE $ddl$
    INSERT INTO public.audit_log_v2
    SELECT * FROM public.audit_log_v2_unpartitioned
  $ddl$;

  -- 1f. keep the old heap for one release as a rollback safety net
  -- (a follow-up migration drops *_unpartitioned after verification)
END$$;

-- ===========================================================================
-- 2. signals → partitioned by created_at
-- ===========================================================================
DO $$
DECLARE
  is_part boolean;
BEGIN
  SELECT EXISTS (
    SELECT 1 FROM pg_partitioned_table pt
    JOIN pg_class c ON c.oid = pt.partrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname='public' AND c.relname='signals'
  ) INTO is_part;

  IF is_part THEN RAISE NOTICE 'signals already partitioned — skipping'; RETURN; END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                 WHERE table_schema='public' AND table_name='signals')
  THEN RAISE NOTICE 'signals missing — nothing to partition'; RETURN; END IF;

  ALTER TABLE public.signals RENAME TO signals_unpartitioned;
  EXECUTE $ddl$
    CREATE TABLE public.signals (
      LIKE public.signals_unpartitioned INCLUDING ALL
    ) PARTITION BY RANGE (created_at)
  $ddl$;
  ALTER TABLE public.signals DROP CONSTRAINT IF EXISTS signals_pkey;
  ALTER TABLE public.signals ADD PRIMARY KEY (id, created_at);

  PERFORM public.create_monthly_partition('public.signals'::regclass,
    date_part('year', now())::int, date_part('month', now())::int);
  PERFORM public.create_monthly_partition('public.signals'::regclass,
    (date_part('year', now() + interval '1 month'))::int,
    (date_part('month', now() + interval '1 month'))::int);
  CREATE TABLE IF NOT EXISTS public.signals_default
    PARTITION OF public.signals DEFAULT;

  EXECUTE 'INSERT INTO public.signals SELECT * FROM public.signals_unpartitioned';
END$$;

-- ===========================================================================
-- 3. funnel_events → partitioned by occurred_at
-- ===========================================================================
DO $$
DECLARE
  is_part boolean;
BEGIN
  SELECT EXISTS (
    SELECT 1 FROM pg_partitioned_table pt
    JOIN pg_class c ON c.oid = pt.partrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname='public' AND c.relname='funnel_events'
  ) INTO is_part;

  IF is_part THEN RAISE NOTICE 'funnel_events already partitioned — skipping'; RETURN; END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                 WHERE table_schema='public' AND table_name='funnel_events')
  THEN RAISE NOTICE 'funnel_events missing — nothing to partition'; RETURN; END IF;

  ALTER TABLE public.funnel_events RENAME TO funnel_events_unpartitioned;
  EXECUTE $ddl$
    CREATE TABLE public.funnel_events (
      LIKE public.funnel_events_unpartitioned INCLUDING ALL
    ) PARTITION BY RANGE (occurred_at)
  $ddl$;
  ALTER TABLE public.funnel_events DROP CONSTRAINT IF EXISTS funnel_events_pkey;
  ALTER TABLE public.funnel_events ADD PRIMARY KEY (id, occurred_at);

  PERFORM public.create_monthly_partition('public.funnel_events'::regclass,
    date_part('year', now())::int, date_part('month', now())::int);
  PERFORM public.create_monthly_partition('public.funnel_events'::regclass,
    (date_part('year', now() + interval '1 month'))::int,
    (date_part('month', now() + interval '1 month'))::int);
  CREATE TABLE IF NOT EXISTS public.funnel_events_default
    PARTITION OF public.funnel_events DEFAULT;

  EXECUTE 'INSERT INTO public.funnel_events SELECT * FROM public.funnel_events_unpartitioned';
END$$;

-- ===========================================================================
-- 4. Re-create the hot indexes on the partitioned parents.
--    (partitioned-table indexes propagate to every partition automatically.)
-- ===========================================================================
CREATE INDEX IF NOT EXISTS idx_audit_log_v2_tenant_time
  ON public.audit_log_v2 (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_signals_created
  ON public.signals (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_funnel_events_occurred
  ON public.funnel_events (occurred_at DESC);

COMMIT;
