-- v11.0 T6104 — Push talent to employer (recommendation records).
--
-- When a candidate↔role match succeeds the platform snapshots the full
-- resume + contact info into a recommendation record and pushes it to the
-- employer (the org that owns the role). The snapshot is immutable so the
-- employer always sees exactly what was matched at push time, even if the
-- candidate later edits their profile.
--
-- Access model (甲方合同要求):
--   * employer (client role, owns org_id)   → sees recommendation summary
--     (score + reasons + skill gaps + risks) AND the full resume snapshot
--     + contact info for recommendations pushed to their org;
--   * platform admin                        → everything above for every org,
--     plus resume PDF download / export.
--
-- PII columns (resume_snapshot, contact_info) are jsonb so we can redact /
-- reshape without a schema migration, and they sit under the v10.0
-- pii_encrypted_values KMS layer for at-rest encryption when that is enabled.

BEGIN;

-- ---------------------------------------------------------------------------
-- recommendations — one pushed talent↔role recommendation per org
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.recommendations (
    id              BIGSERIAL PRIMARY KEY,
    candidate_id    TEXT NOT NULL,
    role_id         TEXT NOT NULL,
    org_id          TEXT NOT NULL,                -- employer org that owns the role
    tenant_id       UUID,                         -- v8.0 multi-tenant column (back-filled)

    match_score     INTEGER NOT NULL DEFAULT 0
                      CHECK (match_score >= 0 AND match_score <= 100),
    match_reasons   JSONB NOT NULL DEFAULT '[]'::jsonb,   -- ["技能匹配 5/5", "同城"]
    skill_gaps      JSONB NOT NULL DEFAULT '[]'::jsonb,   -- ["缺 K8s 经验"]
    risks           JSONB NOT NULL DEFAULT '[]'::jsonb,   -- ["到岗不确定", "薪资偏高"]

    resume_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,   -- immutable full resume
    contact_info    JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {email, phone, linkedin_url}

    -- candidate/role denormalised for list display without a join
    candidate_name  TEXT NOT NULL DEFAULT '',
    candidate_title TEXT NOT NULL DEFAULT '',
    role_title      TEXT NOT NULL DEFAULT '',
    company_name    TEXT NOT NULL DEFAULT '',

    status          TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'viewed', 'accepted', 'rejected')),
    viewed_at       TIMESTAMPTZ,
    accepted_at     TIMESTAMPTZ,
    rejected_at     TIMESTAMPTZ,
    rejected_reason TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recommendations_org
    ON public.recommendations(org_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendations_role
    ON public.recommendations(role_id);

CREATE INDEX IF NOT EXISTS idx_recommendations_candidate
    ON public.recommendations(candidate_id);

CREATE INDEX IF NOT EXISTS idx_recommendations_status
    ON public.recommendations(org_id, status);

CREATE INDEX IF NOT EXISTS idx_recommendations_tenant
    ON public.recommendations(tenant_id);

COMMENT ON TABLE public.recommendations IS
    'T6104 — a talent↔role match pushed to an employer org. Snapshot of the '
    'full resume + contact info is captured at push time. Status lifecycle: '
    'pending → viewed → accepted | rejected.';

-- ---------------------------------------------------------------------------
-- Row Level Security
--
--   * service_role / platform admin: full access to every org (the FastAPI
--     backend reads/writes via the service-role admin client);
--   * authenticated employer: SELECT only the recommendations whose org_id
--     matches the JWT claim ``raw_app_meta_data.org_id`` (or
--     ``user_metadata.org_id``). Writes go through the backend, not the anon
--     key, so employers get read-only RLS here.
-- ---------------------------------------------------------------------------
ALTER TABLE public.recommendations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS recommendations_service_all ON public.recommendations;
CREATE POLICY recommendations_service_all
    ON public.recommendations
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS recommendations_employer_select ON public.recommendations;
CREATE POLICY recommendations_employer_select
    ON public.recommendations
    FOR SELECT
    TO authenticated
    USING (
        org_id = COALESCE(
            NULLIF(current_setting('request.jwt.claim.org_id', true), ''),
            NULLIF(current_setting('request.jwt.claims', true)::jsonb
                       ->> 'org_id', ''),
            NULLIF(current_setting('request.jwt.claims', true)::jsonb
                       -> 'user_metadata' ->> 'org_id', '')
        )
    );

-- Download / export of resume PII is admin-only by policy. The actual
-- enforcement happens in the backend (require_role(admin)); this RLS comment
-- documents the contract. The anon/authenticated key cannot DELETE/UPDATE
-- because no such policy is defined, so updates are forced through the
-- service-role admin client inside the FastAPI layer.

COMMENT ON POLICY recommendations_employer_select IS
    'Employers can SELECT only recommendations pushed to their own org. '
    'Resume PDF download/export is admin-only (enforced in the backend).';

-- ---------------------------------------------------------------------------
-- updated_at bump trigger (mirrors the v9 consolidated trigger convention)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.touch_recommendation_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_recommendations_updated_at ON public.recommendations;
CREATE TRIGGER trg_recommendations_updated_at
    BEFORE UPDATE ON public.recommendations
    FOR EACH ROW
    EXECUTE FUNCTION public.touch_recommendation_updated_at();

COMMIT;
