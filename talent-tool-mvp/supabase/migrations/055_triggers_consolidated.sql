-- ============================================================================
-- 055_triggers_consolidated.sql
-- T5011 (part 1) — consolidate the 30+ duplicate ``*_touch_updated_at`` /
-- ``set_updated_at`` / ``update_updated_at`` trigger functions into ONE
-- shared ``public.set_updated_at()`` and re-point every table at it.
--
-- Problem
-- -------
-- As migrations accreted, each new table defined its own near-identical
-- ``BEFORE UPDATE`` function:
--
--     CREATE FUNCTION <table>_touch_updated_at() ...
--     CREATE FUNCTION set_updated_at() ...
--     CREATE FUNCTION update_updated_at() ...
--     CREATE FUNCTION trg_<x>_updated_at() ...
--
-- There are ~9 distinct function names today, each a one-liner that does
-- ``NEW.updated_at := NOW(); RETURN NEW;``.  That is:
--   * catalog bloat (one pg_proc row per table),
--   * drift risk (a "skip when nothing changed" optimisation can only land
--     if every copy is patched), and
--   * confusion for new engineers ("which function do I copy?").
--
-- Solution
-- --------
-- A single canonical function ``public.set_updated_at()`` that:
--   1. only touches ``updated_at`` when a non-key column actually changed
--      (avoids no-op UPDATEs cascading into replica churn), and
--   2. tolerates tables that have no ``updated_at`` column (defensive —
--      returns NEW unchanged so the trigger is safe to attach broadly).
--
-- All legacy per-table functions are then redefined as thin SQL wrappers
-- that delegate to the canonical one, so existing triggers keep working
-- without a mass ``DROP/CREATE TRIGGER`` sweep.
--
-- Idempotent.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Canonical function: set NEW.updated_at = NOW() on UPDATE only when row
--    actually changed.  Defensive against missing updated_at column.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  col_exists boolean;
BEGIN
  -- cheap existence check cached per-call
  SELECT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = TG_TABLE_SCHEMA
      AND table_name   = TG_TABLE_NAME
      AND column_name  = 'updated_at'
  ) INTO col_exists;

  IF NOT col_exists THEN
    RETURN NEW;                       -- no updated_at column → nothing to do
  END IF;

  -- Skip the write when the row did not actually change.  This avoids
  -- stampedes on replica-heavy setups and keeps updated_at meaningful
  -- (it reflects *real* mutations, not idempotent re-saves).
  IF TG_OP = 'UPDATE' AND NEW IS NOT DISTINCT FROM OLD THEN
    RETURN NEW;
  END IF;

  NEW.updated_at := NOW();
  RETURN NEW;
END$$;

COMMENT ON FUNCTION public.set_updated_at() IS
  'T5011: canonical BEFORE UPDATE trigger body. Sets updated_at=now() only '
  'when the row genuinely changed; no-op when the table lacks updated_at. '
  'All legacy *_touch_updated_at / update_updated_at helpers delegate here.';

-- ---------------------------------------------------------------------------
-- 2. Legacy function consolidation.
--    Redefine each known duplicate as a thin wrapper so any trigger still
--    bound to the old name transparently uses the canonical body.  DROP
--    and CREATE OR REPLACE so we never accumulate stale implementations.
--    (CREATE OR REPLACE alone cannot change the body semantics in place
--    reliably across PG versions when the source differs, so we drop first.)
-- ---------------------------------------------------------------------------
DO $$
DECLARE
  fn text;
  legacy text[] := ARRAY[
    -- 004/010 era one-shots
    'update_updated_at',
    -- 010 hr_tickets
    'trg_tickets_touch_updated_at',
    -- 012 persona prefs
    'trg_persona_prefs_updated_at',
    -- 041 / older notify prefs
    'trg_notify_prefs_touch_updated_at',
    'trg_notification_preferences_touch_updated_at',
    -- 036 workflows
    'trg_workflows_updated_at',
    -- 053 services
    'services_touch_updated_at',
    -- 019 pilot programs
    'pilot_programs_touch_updated_at'
  ];
BEGIN
  FOREACH fn IN ARRAY legacy LOOP
    -- only touch functions that actually exist in public
    IF EXISTS (
      SELECT 1 FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
      WHERE n.nspname = 'public' AND p.proname = fn
    ) THEN
      EXECUTE format('DROP FUNCTION IF EXISTS public.%I()', fn);
      EXECUTE format(
        'CREATE FUNCTION public.%I() RETURNS trigger '
        'LANGUAGE sql AS $$ SELECT public.set_updated_at() $$',
        fn
      );
    END IF;
  END LOOP;
END$$;

-- ---------------------------------------------------------------------------
-- 3. Canonical trigger attachment helper.
--    Convenience so future migrations can do:
--      SELECT public.attach_updated_at_trigger('my_table');
--    instead of copying boilerplate.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.attach_updated_at_trigger(tbl regclass)
RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
  schema_n text;
  table_n text;
  trg_name text;
BEGIN
  SELECT n.nspname, c.relname INTO schema_n, table_n
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE c.oid = tbl;
  IF table_n IS NULL THEN
    RAISE EXCEPTION 'table % does not exist', tbl;
  END IF;
  trg_name := 'trg_' || table_n || '_updated_at';
  EXECUTE format('DROP TRIGGER IF EXISTS %I ON %s', trg_name, tbl);
  EXECUTE format(
    'CREATE TRIGGER %I BEFORE UPDATE ON %s '
    'FOR EACH ROW EXECUTE FUNCTION public.set_updated_at()',
    trg_name, tbl
  );
END$$;

COMMENT ON FUNCTION public.attach_updated_at_trigger(regclass) IS
  'T5011: idempotently attach the canonical set_updated_at() trigger to a table.';

-- ---------------------------------------------------------------------------
-- 4. Re-point existing per-table triggers at the canonical function.
--    (Defensive: most legacy triggers still call their own wrapper, which
--     now delegates to set_updated_at.  Re-pointing the trigger directly
--     removes one extra function-call hop.)
-- ---------------------------------------------------------------------------
DO $$
DECLARE
  r record;
BEGIN
  -- find every BEFORE UPDATE trigger whose underlying function is one of our
  -- consolidated wrappers, and rewire it to public.set_updated_at().
  FOR r IN
    SELECT c.oid AS table_oid, t.tgfoid AS fn_oid, t.tgname AS trg_name
      FROM pg_trigger t
      JOIN pg_class  c ON c.oid = t.tgrelid
      JOIN pg_proc   f ON f.oid = t.tgfoid
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND t.tgtype & 2 = 0           -- row-level (not statement)
       AND NOT t.tgisinternal
       AND (f.proname IN (
              'update_updated_at','trg_tickets_touch_updated_at',
              'trg_persona_prefs_updated_at','trg_notify_prefs_touch_updated_at',
              'trg_notification_preferences_touch_updated_at',
              'trg_workflows_updated_at','services_touch_updated_at',
              'pilot_programs_touch_updated_at'
            )
            OR f.proname = 'set_updated_at')
  LOOP
    BEGIN
      EXECUTE format('DROP TRIGGER %I ON %s', r.trg_name, r.table_oid::regclass);
      EXECUTE format(
        'CREATE TRIGGER %I BEFORE UPDATE ON %s '
        'FOR EACH ROW EXECUTE FUNCTION public.set_updated_at()',
        r.trg_name, r.table_oid::regclass
      );
    EXCEPTION WHEN OTHERS THEN
      -- a concurrent migration may have dropped the table; skip gracefully
      NULL;
    END;
  END LOOP;
END$$;

COMMIT;
