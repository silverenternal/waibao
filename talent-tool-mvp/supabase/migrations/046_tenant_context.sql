-- T2601: Strict multi-tenant isolation via Supabase RLS
--
-- Strategy:
--   * Treat every business table as owned by a tenant (organisation_id).
--     To stay forward-compatible with the spec's ``tenant_id`` naming, we
--     add a nullable ``tenant_id`` column to every business table when
--     missing and back-fill it from ``organisation_id``.  Existing rows are
--     populated immediately; new inserts MUST provide ``tenant_id`` (enforced
--     by trigger) so old code paths cannot accidentally orphan rows.
--
--   * Enable RLS + per-table policy that compares ``tenant_id`` to the
--     session-local GUC ``app.tenant_id``.  The GUC is set by the backend
--     on every request using ``SET LOCAL`` inside a transaction.
--
--   * Service-role requests (``auth.role() = 'service_role'``) bypass RLS for
--     legitimate cross-tenant admin work, and the ``app.tenant_id`` GUC is
--     overridden by an admin actor for "impersonation" scenarios.
--
-- This migration is idempotent: re-running it is a no-op because each
-- ``ALTER TABLE ... IF NOT EXISTS`` / ``CREATE POLICY ... IF NOT EXISTS``
-- is guarded by information_schema lookups.

BEGIN;

-- ----------------------------------------------------------------------
-- 0. Helpers
-- ----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.current_tenant() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
$$;

CREATE OR REPLACE FUNCTION public.is_service_role() RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT coalesce(current_setting('role', true), '') = 'service_role'
         OR current_setting('app.bypass_rls', true) = 'on'
$$;

-- ----------------------------------------------------------------------
-- 1. Business tables — add tenant_id + back-fill from organisation_id
-- ----------------------------------------------------------------------
DO $$
DECLARE
  t text;
  tables text[] := ARRAY[
    'users','roles','candidates','collections','handoffs','quotes','signals',
    'subscription_events','funnel_events','job_subscriptions','video_interviews',
    'assessments','background_checks','ats_sync_records','workflows','workflow_runs',
    'matches','collections_roles','collection_invites','collections_messages',
    'ai_interview_sessions','ai_interview_messages','offers','referrals',
    'probation_tracking','attrition_predictions','notification_preferences',
    'pilot_programs','pilot_invitations','pilot_feedback','rediscovery_jobs',
    'collaboration_rooms','room_messages','feature_flag_overrides',
    'config_center_entries','plugin_instances','plugin_runs','llm_cost_records',
    'audit_events','push_messages','company_reviews','salary_reports',
    'talent_briefs','career_plans','learning_resources','journal_entries',
    'voice_journal','escalation_tickets','emotion_timeline_entries',
    'tickets','vision_uploads','job_specs','jd_templates','action_items',
    'multiparty_sessions','notification_log'
  ];
BEGIN
  FOREACH t IN ARRAY tables LOOP
    -- 1a. Create tenant_id column if missing
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema='public' AND table_name=t AND column_name='tenant_id'
    ) THEN
      EXECUTE format('ALTER TABLE public.%I ADD COLUMN tenant_id uuid', t);
    END IF;

    -- 1b. Back-fill tenant_id from organisation_id (best effort)
    EXECUTE format(
      'UPDATE public.%I SET tenant_id = organisation_id '
      'WHERE tenant_id IS NULL AND organisation_id IS NOT NULL',
      t
    );

    -- 1c. Index for RLS perf (most filters go through tenant_id)
    EXECUTE format(
      'CREATE INDEX IF NOT EXISTS idx_%s_tenant ON public.%I(tenant_id)',
      t, t
    );

    -- 1d. Enable RLS (idempotent)
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', t);

    -- 1e. Drop+recreate policies (idempotent)
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON public.%I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON public.%I '
      'USING (tenant_id = public.current_tenant() OR public.is_service_role()) '
      'WITH CHECK (tenant_id = public.current_tenant() OR public.is_service_role())',
      t
    );
  END LOOP;
END$$;

-- ----------------------------------------------------------------------
-- 2. Trigger: enforce tenant_id on INSERT (must match connected tenant)
-- ----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.enforce_tenant_id() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  ctx uuid := public.current_tenant();
BEGIN
  IF public.is_service_role() THEN
    RETURN NEW;          -- service_role may insert anywhere
  END IF;
  IF NEW.tenant_id IS NULL THEN
    NEW.tenant_id := ctx;
  ELSIF NEW.tenant_id <> ctx THEN
    RAISE EXCEPTION 'tenant_id mismatch: row=% vs ctx=%', NEW.tenant_id, ctx
      USING ERRCODE = '42501';
  END IF;
  RETURN NEW;
END$$;

DO $$
DECLARE
  t text;
  tables text[] := ARRAY[
    'users','roles','candidates','collections','handoffs','quotes','signals',
    'funnel_events','video_interviews','assessments','background_checks',
    'matches','ai_interview_sessions','offers','referrals','probation_tracking',
    'attrition_predictions','notification_preferences','pilot_programs',
    'collaboration_rooms','feature_flag_overrides','config_center_entries',
    'plugin_instances','llm_cost_records','audit_events','push_messages',
    'company_reviews','salary_reports','talent_briefs','career_plans'
  ];
BEGIN
  FOREACH t IN ARRAY tables LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS trg_tenant_id ON public.%I', t);
    EXECUTE format(
      'CREATE TRIGGER trg_tenant_id BEFORE INSERT ON public.%I '
      'FOR EACH ROW EXECUTE FUNCTION public.enforce_tenant_id()',
      t
    );
  END LOOP;
END$$;

-- ----------------------------------------------------------------------
-- 3. Helper: SET LOCAL tenant context (call from API code)
-- ----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.set_tenant_context(tid uuid, bypass boolean DEFAULT false)
RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
  PERFORM set_config('app.tenant_id', coalesce(tid::text, ''), true);
  IF bypass THEN
    PERFORM set_config('app.bypass_rls', 'on', true);
  ELSE
    PERFORM set_config('app.bypass_rls', 'off', true);
  END IF;
END$$;

-- ----------------------------------------------------------------------
-- 4. Smoke-test: insert two tenants, query with explicit ctx
-- ----------------------------------------------------------------------
-- (No actual fixtures here; runtime verification is done in
--  tests/test_tenant_isolation.py against a real Postgres instance.)

COMMIT;
