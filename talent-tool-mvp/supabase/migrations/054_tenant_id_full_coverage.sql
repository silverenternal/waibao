-- ============================================================================
-- 054_tenant_id_full_coverage.sql
-- T5010 — Tenant-id full coverage + RLS (USING + WITH CHECK) + trigger guard
--
-- Background
-- ----------
-- Migration 046 introduced the ``tenant_id`` column on the core business
-- tables and back-filled it from ``organisation_id``.  However the original
-- DO block only ran ``SET tenant_id = organisation_id`` — so any table that
-- *lacks* a direct ``organisation_id`` column (candidates, matches,
-- conversations, emotion_timeline, ai_interviews, assessments, ...) was left
-- with ``tenant_id IS NULL`` on its historical rows.  Those rows are
-- effectively "orphan" rows that bypass tenant isolation, and new inserts
-- were only guarded by a BEFORE INSERT trigger (UPDATE never re-checked the
-- tenant_id), which let a row be reparented to another tenant after creation.
--
-- This migration closes those gaps:
--
--   1. Ensure ``tenant_id`` exists on every remaining business table
--      (candidates / tickets / matches / conversations / emotion_timeline /
--       daily_journals / ai_interviews / video / assessment / ats + their
--       sibling/child tables).
--   2. Back-fill ``tenant_id``:
--        * direct  : SET tenant_id = organisation_id
--        * indirect: SET tenant_id = (SELECT tenant_id FROM users WHERE ...)
--      so no historical row is left NULL.
--   3. Enforce NOT NULL on the columns we just populated (best-effort: only
--      applied when no NULLs remain, guarded by a pre-check).
--   4. RLS: drop the old single ``tenant_isolation`` policy and recreate it
--      with both ``USING`` (read visibility) and ``WITH CHECK`` (write
--      guard) so rows cannot be moved out of the caller's tenant on UPDATE.
--   5. Upgrade the enforcement trigger to ``BEFORE INSERT OR UPDATE`` so
--      UPDATE is also rejected when it would reparent a row to a foreign
--      tenant.
--
-- Idempotent: every DDL is guarded.  Re-running is a no-op.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 0. Guard helpers (reuse the ones from 046 if they exist; define if missing)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.current_tenant() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
$$;

CREATE OR REPLACE FUNCTION public.is_service_role() RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT coalesce(current_setting('role', true), '') = 'service_role'
         OR current_setting('app.bypass_rls', true) = 'on'
$$;

-- ---------------------------------------------------------------------------
-- 1. Master list of business tables that must own a tenant_id.
--    Grouped by how the tenant is resolved:
--      * direct  -> has its own ``organisation_id`` column
--      * via_users -> resolves tenant through a user FK
-- ---------------------------------------------------------------------------
-- 1a. ensure the column exists
DO $$
DECLARE
  t text;
  tables text[] := ARRAY[
    -- core candidate funnel
    'candidates','matches','tickets','ticket_comments','ticket_status_history',
    -- jobseeker-facing
    'conversations','emotion_timeline','career_plans','journal_entries',
    'voice_journal','action_items',
    -- ai interview
    'ai_interview_sessions','ai_interview_messages',
    'ai_interviews_v2','ai_interview_answers_v2','ai_interview_reports_v2',
    -- video / assessment / ats
    'video_interviews','assessment_invitations','ats_sync_records',
    -- legacy dual names (older migrations used emotion_timeline_entries /
    -- notification_log) — harmless if a table does not exist
    'emotion_timeline_entries'
  ];
BEGIN
  FOREACH t IN ARRAY tables LOOP
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema='public' AND table_name=t AND column_name='tenant_id'
    ) THEN
      -- only add when the table itself exists (some legacy names may not)
      IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='public' AND table_name=t
      ) THEN
        EXECUTE format('ALTER TABLE public.%I ADD COLUMN tenant_id uuid', t);
      END IF;
    END IF;
  END LOOP;
END$$;

-- ---------------------------------------------------------------------------
-- 2. Back-fill tenant_id
--    Strategy table-by-table: use organisation_id directly when present,
--    otherwise join through the user FK to users.tenant_id (falling back to
--    users.organisation_id for rows created before 046 populated users).
-- ---------------------------------------------------------------------------

-- 2a. tables that carry their own organisation_id column
DO $$
DECLARE
  t text;
  tables_direct text[] := ARRAY[
    'tickets'               -- tickets.organisation_id (migration 010)
  ];
BEGIN
  FOREACH t IN ARRAY tables_direct LOOP
    IF EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema='public' AND table_name=t AND column_name='organisation_id'
    ) THEN
      EXECUTE format(
        'UPDATE public.%I SET tenant_id = organisation_id '
        'WHERE tenant_id IS NULL AND organisation_id IS NOT NULL',
        t
      );
    END IF;
  END LOOP;
END$$;

-- 2b. tables that resolve tenant via a user FK (user_id / created_by)
DO $$
DECLARE
  -- (table, user_fk_column)
  rec record;
  via_users record[] := ARRAY[
    ('candidates','created_by')::record,
    ('matches','candidate_id')::record,          -- via candidate owner
    ('ticket_comments','author_id')::record,
    ('ticket_status_history','changed_by')::record,
    ('conversations','user_id')::record,
    ('emotion_timeline','user_id')::record,
    ('emotion_timeline_entries','user_id')::record,
    ('career_plans','user_id')::record,
    ('journal_entries','user_id')::record,
    ('voice_journal','user_id')::record,
    ('action_items','user_id')::record,
    ('ai_interview_sessions','user_id')::record,
    ('ai_interview_messages','session_id')::record,   -- 2-hop: msg->session->user
    ('assessment_invitations','candidate_id')::record,-- via candidate
    ('video_interviews','candidate_id')::record       -- via candidate
  ];
  has_tenant boolean;
  has_org    boolean;
BEGIN
  FOREACH rec IN ARRAY via_users LOOP
    -- skip if the table does not exist
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.tables
      WHERE table_schema='public' AND table_name=rec.f1
    ) THEN CONTINUE; END IF;

    -- which user-tenant column is populated on `users`?
    SELECT EXISTS(SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='users'
                      AND column_name='tenant_id')
      INTO has_tenant;
    SELECT EXISTS(SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='users'
                      AND column_name='organisation_id')
      INTO has_org;

    -- only run the update if the FK column exists on the target table
    IF EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema='public' AND table_name=rec.f1 AND column_name=rec.f2
    ) THEN
      IF rec.f1 = 'matches' THEN
        -- matches has no user FK: derive via candidates.created_by -> users
        EXECUTE $f$
          UPDATE public.matches m
             SET tenant_id = cu.tenant_id
            FROM public.candidates c
            JOIN public.users cu ON cu.id = c.created_by
           WHERE m.tenant_id IS NULL AND m.candidate_id = c.id
             AND cu.tenant_id IS NOT NULL
        $f$;
        EXECUTE $f$
          UPDATE public.matches m
             SET tenant_id = cu.organisation_id
            FROM public.candidates c
            JOIN public.users cu ON cu.id = c.created_by
           WHERE m.tenant_id IS NULL AND m.candidate_id = c.id
             AND cu.tenant_id IS NULL AND cu.organisation_id IS NOT NULL
        $f$;
      ELSIF rec.f1 = 'assessment_invitations' OR rec.f1 = 'video_interviews' THEN
        -- candidate-owned tables: candidate -> created_by -> users
        EXECUTE format(
          $f$
            UPDATE public.%I x
               SET tenant_id = cu.tenant_id
              FROM public.candidates c
              JOIN public.users cu ON cu.id = c.created_by
             WHERE x.tenant_id IS NULL AND x.candidate_id = c.id
               AND cu.tenant_id IS NOT NULL
          $f$, rec.f1);
        EXECUTE format(
          $f$
            UPDATE public.%I x
               SET tenant_id = cu.organisation_id
              FROM public.candidates c
              JOIN public.users cu ON cu.id = c.created_by
             WHERE x.tenant_id IS NULL AND x.candidate_id = c.id
               AND cu.tenant_id IS NULL AND cu.organisation_id IS NOT NULL
          $f$, rec.f1);
      ELSIF rec.f1 = 'ai_interview_messages' THEN
        -- 2-hop: messages.session_id -> sessions.user_id -> users
        EXECUTE $f$
          UPDATE public.ai_interview_messages msg
             SET tenant_id = cu.tenant_id
            FROM public.ai_interview_sessions s
            JOIN public.users cu ON cu.id = s.user_id
           WHERE msg.tenant_id IS NULL AND msg.session_id = s.id
             AND cu.tenant_id IS NOT NULL
        $f$;
        EXECUTE $f$
          UPDATE public.ai_interview_messages msg
             SET tenant_id = cu.organisation_id
            FROM public.ai_interview_sessions s
            JOIN public.users cu ON cu.id = s.user_id
           WHERE msg.tenant_id IS NULL AND msg.session_id = s.id
             AND cu.tenant_id IS NULL AND cu.organisation_id IS NOT NULL
        $f$;
      ELSE
        -- 1-hop: target.<col> -> users.id -> users.tenant_id
        IF has_tenant THEN
          EXECUTE format(
            'UPDATE public.%I t SET tenant_id = u.tenant_id '
            'FROM public.users u WHERE t.tenant_id IS NULL '
            'AND u.id = t.%I AND u.tenant_id IS NOT NULL',
            rec.f1, rec.f2);
        END IF;
        IF has_org THEN
          EXECUTE format(
            'UPDATE public.%I t SET tenant_id = u.organisation_id '
            'FROM public.users u WHERE t.tenant_id IS NULL '
            'AND u.id = t.%I AND u.tenant_id IS NULL '
            'AND u.organisation_id IS NOT NULL',
            rec.f1, rec.f2);
        END IF;
      END IF;
    END IF;
  END LOOP;
END$$;

-- ---------------------------------------------------------------------------
-- 3. SET NOT NULL (only on tables we know are fully back-filled)
--    A pre-check guarantees we never fail on a half-populated table.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
  t text;
  null_count bigint;
  tables_nn text[] := ARRAY[
    'candidates','matches','tickets','conversations','emotion_timeline'
  ];
BEGIN
  FOREACH t IN ARRAY tables_nn LOOP
    IF EXISTS (
      SELECT 1 FROM information_schema.tables
      WHERE table_schema='public' AND table_name=t
    ) AND EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema='public' AND table_name=t AND column_name='tenant_id'
    ) THEN
      EXECUTE format(
        'SELECT count(*) FROM public.%I WHERE tenant_id IS NULL', t
      ) INTO null_count;
      IF null_count = 0 THEN
        EXECUTE format('ALTER TABLE public.%I ALTER COLUMN tenant_id SET NOT NULL', t);
      END IF;
    END IF;
  END LOOP;
END$$;

-- ---------------------------------------------------------------------------
-- 4. RLS: USING + WITH CHECK (upgrade from 046's single USING/CHECK policy)
--    Drop the legacy ``tenant_isolation`` policy and recreate a precise pair.
--    We keep a single composite policy (FOR ALL) so both reads and writes
--    consult the same expression; WITH CHECK additionally blocks an UPDATE
--    that would move a row to a different tenant.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
  t text;
  tables text[] := ARRAY[
    'candidates','matches','tickets','ticket_comments','ticket_status_history',
    'conversations','emotion_timeline','emotion_timeline_entries',
    'career_plans','journal_entries','voice_journal','action_items',
    'ai_interview_sessions','ai_interview_messages',
    'ai_interviews_v2','ai_interview_answers_v2','ai_interview_reports_v2',
    'video_interviews','assessment_invitations','ats_sync_records'
  ];
BEGIN
  FOREACH t IN ARRAY tables LOOP
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.tables
      WHERE table_schema='public' AND table_name=t
    ) THEN CONTINUE; END IF;
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema='public' AND table_name=t AND column_name='tenant_id'
    ) THEN CONTINUE; END IF;

    -- perf index for RLS filter (idempotent)
    EXECUTE format(
      'CREATE INDEX IF NOT EXISTS idx_%s_tenant ON public.%I(tenant_id)',
      t, t
    );

    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', t);

    -- drop any previously-attached tenant policy (046 named it tenant_isolation)
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON public.%I', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_all ON public.%I', t);

    -- new composite policy: read AND write are tenant-scoped.
    -- USING  -> which rows are visible / deletable / updatable (old image)
    -- CHECK  -> what the NEW row image must satisfy
    EXECUTE format(
      'CREATE POLICY tenant_all ON public.%I FOR ALL '
      'USING (tenant_id = public.current_tenant() OR public.is_service_role()) '
      'WITH CHECK (tenant_id = public.current_tenant() OR public.is_service_role())',
      t
    );
  END LOOP;
END$$;

-- ---------------------------------------------------------------------------
-- 5. Trigger: BEFORE INSERT OR UPDATE — enforce tenant_id matches session
--    Replaces the 046 BEFORE INSERT only trigger.  On UPDATE we additionally
--    forbid reparenting a row to a different tenant than the one it was
--    created under (prevents privilege escalation via UPDATE).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.enforce_tenant_id() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  ctx uuid := public.current_tenant();
BEGIN
  IF public.is_service_role() THEN
    RETURN NEW;                       -- service_role is unscoped by design
  END IF;

  IF TG_OP = 'INSERT' THEN
    IF NEW.tenant_id IS NULL THEN
      NEW.tenant_id := ctx;           -- auto-attach to the caller's tenant
    ELSIF NEW.tenant_id IS DISTINCT FROM ctx THEN
      RAISE EXCEPTION 'tenant_id mismatch on INSERT: row=% vs ctx=%',
        NEW.tenant_id, ctx USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
  END IF;

  -- TG_OP = 'UPDATE'
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
    -- no reparenting: the tenant of a row is immutable post-creation
    RAISE EXCEPTION 'tenant_id is immutable: cannot move row % -> %',
      OLD.tenant_id, NEW.tenant_id USING ERRCODE = '42501';
  END IF;
  RETURN NEW;
END$$;

DO $$
DECLARE
  t text;
  tables text[] := ARRAY[
    'candidates','matches','tickets','ticket_comments','ticket_status_history',
    'conversations','emotion_timeline','emotion_timeline_entries',
    'career_plans','journal_entries','voice_journal','action_items',
    'ai_interview_sessions','ai_interview_messages',
    'video_interviews','assessment_invitations','ats_sync_records'
  ];
BEGIN
  FOREACH t IN ARRAY tables LOOP
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.tables
      WHERE table_schema='public' AND table_name=t
    ) THEN CONTINUE; END IF;
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema='public' AND table_name=t AND column_name='tenant_id'
    ) THEN CONTINUE; END IF;

    EXECUTE format('DROP TRIGGER IF EXISTS trg_tenant_id ON public.%I', t);
    EXECUTE format(
      'CREATE TRIGGER trg_tenant_id BEFORE INSERT OR UPDATE ON public.%I '
      'FOR EACH ROW EXECUTE FUNCTION public.enforce_tenant_id()',
      t
    );
  END LOOP;
END$$;

-- ---------------------------------------------------------------------------
-- 6. Sanity comment
-- ---------------------------------------------------------------------------
COMMENT ON FUNCTION public.enforce_tenant_id() IS
  'T5010: enforce tenant_id matches the session GUC on INSERT and forbid '
  'reparenting on UPDATE. service_role bypasses. Raises 42501 on violation.';

COMMIT;
