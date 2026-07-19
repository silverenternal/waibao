-- v11.2 T6302 — Identity verification + compensation/benefits dimensions +
-- communication channels + profile versioning.
--
-- This migration adds the v11.2 data model needed for the 甲方 (client)
-- acceptance flow:
--
--   (1) candidates — identity verification lifecycle + 五险一金 / 出差
--       expectations. The identity lifecycle is a three-stage enum per
--       document (id_card / education_doc / resume) plus a rolled-up
--       ``identity_status``:
--         pending   = 待上传 (not verified yet)
--         submitted = 待审核 (documents uploaded, awaiting review)
--         verified  = 已认证 (all three documents verified)
--       RULE: identity_status can only be 'verified' when id_card_status
--       AND education_doc_status AND resume_status are ALL 'verified'.
--       五险一金 / 出差 are HIGH-priority SOFT signals — they only ever
--       sort / rank, never eliminate (甲方: 没有淘汰只做增量). 工作/行业
--       经历 are NOT used for filtering.
--
--   (2) roles — employer-side benefits/travel offerings (五险一金 /
--       公积金 / 出差要求). Also soft scoring dimensions.
--
--   (3) communication_channels — a 1:1 thread per (candidate, role) pair
--       that records who initiated contact (candidate | employer), the
--       match score at the time of contact, and an open/closed status.
--       Visible to the candidate OR the owning org (multi-tenant).
--
--   (4) profile_versions — an append-only versioned snapshot of a
--       candidate's profile so the employer always sees the exact resume
--       that was matched at push time (mirrors recommendations semantics).
--       Visible to the candidate only (plus service/admin).
--
-- Display map (shared with backend services):
--     pending   -> 待上传
--     submitted -> 待审核
--     verified  -> 已认证
--
-- Access model (甲方合同要求):
--   * service_role / platform admin: full access to everything (the FastAPI
--     backend reads/writes via the service-role admin client);
--   * authenticated employer: sees communication_channels for their own org;
--   * authenticated candidate: sees their own communication_channels and
--     their own profile_versions.

BEGIN;

-- ===========================================================================
-- (1) candidates — identity + benefits/travel expectation columns
-- ===========================================================================
ALTER TABLE public.candidates
    ADD COLUMN IF NOT EXISTS identity_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (identity_status IN ('pending', 'submitted', 'verified'));

ALTER TABLE public.candidates
    ADD COLUMN IF NOT EXISTS id_card_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (id_card_status IN ('pending', 'submitted', 'verified'));

ALTER TABLE public.candidates
    ADD COLUMN IF NOT EXISTS education_doc_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (education_doc_status IN ('pending', 'submitted', 'verified'));

ALTER TABLE public.candidates
    ADD COLUMN IF NOT EXISTS resume_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (resume_status IN ('pending', 'submitted', 'verified'));

-- candidate expects 五险一金 (HIGH priority soft signal; never eliminates)
ALTER TABLE public.candidates
    ADD COLUMN IF NOT EXISTS social_insurance_expectation BOOLEAN;

-- travel tolerance: willing | occasional | unwilling (soft signal)
ALTER TABLE public.candidates
    ADD COLUMN IF NOT EXISTS travel_tolerance TEXT
        CHECK (travel_tolerance IS NULL
               OR travel_tolerance IN ('willing', 'occasional', 'unwilling'));

-- when the rolled-up identity_status flipped to 'verified'
ALTER TABLE public.candidates
    ADD COLUMN IF NOT EXISTS identity_verified_at TIMESTAMPTZ;

COMMENT ON COLUMN public.candidates.identity_status IS
    'v11.2 — rolled-up identity verification status. '
    'pending=待上传, submitted=待审核, verified=已认证. '
    'verified ONLY when id_card_status AND education_doc_status AND '
    'resume_status are all verified.';
COMMENT ON COLUMN public.candidates.id_card_status IS
    'v11.2 — id-card (身份证) document verification status '
    '(pending|submitted|verified).';
COMMENT ON COLUMN public.candidates.education_doc_status IS
    'v11.2 — education certificate (学历证明) verification status '
    '(pending|submitted|verified).';
COMMENT ON COLUMN public.candidates.resume_status IS
    'v11.2 — resume (简历) verification status (pending|submitted|verified).';
COMMENT ON COLUMN public.candidates.social_insurance_expectation IS
    'v11.2 — candidate expects 五险一金. HIGH-priority SOFT signal: used '
    'for sort/rank only, never eliminates a candidate.';
COMMENT ON COLUMN public.candidates.travel_tolerance IS
    'v11.2 — travel tolerance (willing|occasional|unwilling). SOFT signal, '
    'never eliminates.';
COMMENT ON COLUMN public.candidates.identity_verified_at IS
    'v11.2 — timestamp when identity_status first became verified.';

-- ===========================================================================
-- (2) roles — benefits/travel offerings columns
-- ===========================================================================
ALTER TABLE public.roles
    ADD COLUMN IF NOT EXISTS offers_social_insurance BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE public.roles
    ADD COLUMN IF NOT EXISTS offers_housing_fund BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE public.roles
    ADD COLUMN IF NOT EXISTS travel_required TEXT NOT NULL DEFAULT 'occasional'
        CHECK (travel_required IN ('none', 'occasional', 'frequent'));

COMMENT ON COLUMN public.roles.offers_social_insurance IS
    'v11.2 — role offers 五险一金. HIGH-priority SOFT signal (sort/rank only).';
COMMENT ON COLUMN public.roles.offers_housing_fund IS
    'v11.2 — role offers 住房公积金 (housing fund). SOFT signal.';
COMMENT ON COLUMN public.roles.travel_required IS
    'v11.2 — role travel requirement (none|occasional|frequent). SOFT signal, '
    'never eliminates.';

-- ===========================================================================
-- (3) communication_channels — 1:1 candidate↔role contact thread
-- ===========================================================================
CREATE TABLE IF NOT EXISTS public.communication_channels (
    id              BIGSERIAL PRIMARY KEY,
    candidate_id    TEXT NOT NULL,                 -- the talent this channel belongs to
    role_id         TEXT NOT NULL,                 -- the role this channel is about
    org_id          TEXT NOT NULL,                 -- employer org that owns the role
    tenant_id       UUID,                          -- v8.0 multi-tenant column (back-filled)

    initiated_by    TEXT NOT NULL                  -- who opened the channel
                      CHECK (initiated_by IN ('candidate', 'employer')),
    match_score     INTEGER                        -- snapshot of match score at contact time
                      CHECK (match_score IS NULL
                             OR (match_score >= 0 AND match_score <= 100)),
    status          TEXT NOT NULL DEFAULT 'open'
                      CHECK (status IN ('open', 'closed')),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (candidate_id, role_id)
);

CREATE INDEX IF NOT EXISTS idx_comm_channels_candidate
    ON public.communication_channels(candidate_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_comm_channels_org
    ON public.communication_channels(org_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_comm_channels_role
    ON public.communication_channels(role_id);

CREATE INDEX IF NOT EXISTS idx_comm_channels_status
    ON public.communication_channels(org_id, status);

CREATE INDEX IF NOT EXISTS idx_comm_channels_tenant
    ON public.communication_channels(tenant_id);

COMMENT ON TABLE public.communication_channels IS
    'v11.2 T6302 — a 1:1 contact thread between a candidate and a role. '
    'Records who initiated (candidate | employer), the match-score snapshot '
    'at contact time, and an open/closed status. UNIQUE(candidate_id, role_id).';
COMMENT ON COLUMN public.communication_channels.initiated_by IS
    'Who opened the channel: candidate or employer.';
COMMENT ON COLUMN public.communication_channels.match_score IS
    'Snapshot of the match score at the time contact was initiated (0-100).';
COMMENT ON COLUMN public.communication_channels.status IS
    'Channel lifecycle: open | closed.';

-- ===========================================================================
-- (4) profile_versions — append-only versioned profile snapshots
-- ===========================================================================
CREATE TABLE IF NOT EXISTS public.profile_versions (
    id              BIGSERIAL PRIMARY KEY,
    candidate_id    TEXT NOT NULL,                 -- the talent this version belongs to
    tenant_id       UUID,                          -- v8.0 multi-tenant column (back-filled)

    version_no      INTEGER NOT NULL,              -- monotonically increasing per candidate
    snapshot        JSONB NOT NULL,                -- immutable full profile snapshot

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- hot path: fetch the latest version for a candidate
CREATE INDEX IF NOT EXISTS idx_profile_versions_candidate_latest
    ON public.profile_versions(candidate_id, version_no DESC);

CREATE INDEX IF NOT EXISTS idx_profile_versions_tenant
    ON public.profile_versions(tenant_id);

COMMENT ON TABLE public.profile_versions IS
    'v11.2 T6302 — append-only versioned snapshot of a candidate profile. '
    'Lets the employer see the exact resume that was matched at push time, '
    'even after the candidate later edits their profile. '
    'Index (candidate_id, version_no DESC) serves the latest-version hot path.';
COMMENT ON COLUMN public.profile_versions.version_no IS
    'Monotonically increasing per-candidate version number (1, 2, 3, ...).';
COMMENT ON COLUMN public.profile_versions.snapshot IS
    'Immutable JSONB snapshot of the full candidate profile at this version.';

-- ===========================================================================
-- Row Level Security
--
--   * service_role / platform admin: full access (the FastAPI backend
--     reads/writes via the service-role admin client);
--   * communication_channels is visible to the candidate (their own
--     channels) OR to the owning org (multi-tenant by org_id);
--   * profile_versions is visible to the candidate only (their own versions).
--
-- The candidate identity is matched against the JWT claim
-- ``raw_app_meta_data.candidate_id`` (or ``user_metadata.candidate_id``);
-- the org identity against ``raw_app_meta_data.org_id`` (or
-- ``user_metadata.org_id``) — mirroring the 061/062 RLS idiom.
-- ===========================================================================
ALTER TABLE public.communication_channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profile_versions ENABLE ROW LEVEL SECURITY;

-- helper: the candidate_id claim resolved from JWT (candidate audience)
CREATE OR REPLACE FUNCTION public.current_candidate_id()
RETURNS TEXT
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(
        NULLIF(current_setting('request.jwt.claim.candidate_id', true), ''),
        NULLIF(current_setting('request.jwt.claims', true)::jsonb
                   ->> 'candidate_id', ''),
        NULLIF(current_setting('request.jwt.claims', true)::jsonb
                   -> 'user_metadata' ->> 'candidate_id', ''),
        NULLIF(current_setting('request.jwt.claims', true)::jsonb
                   -> 'app_metadata' ->> 'candidate_id', '')
    )
$$;

-- helper: the org_id claim resolved from JWT (employer audience) — mirrors 061
CREATE OR REPLACE FUNCTION public.current_org_id()
RETURNS TEXT
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(
        NULLIF(current_setting('request.jwt.claim.org_id', true), ''),
        NULLIF(current_setting('request.jwt.claims', true)::jsonb
                   ->> 'org_id', ''),
        NULLIF(current_setting('request.jwt.claims', true)::jsonb
                   -> 'user_metadata' ->> 'org_id', ''),
        NULLIF(current_setting('request.jwt.claims', true)::jsonb
                   -> 'app_metadata' ->> 'org_id', '')
    )
$$;

COMMENT ON FUNCTION public.current_candidate_id() IS
    'v11.2 — resolves the candidate_id JWT claim (candidate audience).';
COMMENT ON FUNCTION public.current_org_id() IS
    'v11.2 — resolves the org_id JWT claim (employer audience).';

-- --- communication_channels: service_role full access ----------------------
DROP POLICY IF EXISTS comm_channels_service_all ON public.communication_channels;
CREATE POLICY comm_channels_service_all
    ON public.communication_channels
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- --- communication_channels: visible to the candidate OR the owning org ----
DROP POLICY IF EXISTS comm_channels_visible ON public.communication_channels;
CREATE POLICY comm_channels_visible
    ON public.communication_channels
    FOR SELECT
    TO authenticated
    USING (
        public.current_candidate_id() = communication_channels.candidate_id
        OR public.current_org_id() = communication_channels.org_id
    );

-- employers may insert/update only their own org's channels (candidate-side
-- writes go through the backend service-role client).
DROP POLICY IF EXISTS comm_channels_org_write ON public.communication_channels;
CREATE POLICY comm_channels_org_write
    ON public.communication_channels
    FOR ALL
    TO authenticated
    USING (public.current_org_id() = communication_channels.org_id)
    WITH CHECK (public.current_org_id() = communication_channels.org_id);

COMMENT ON POLICY comm_channels_visible IS
    'A communication channel is visible to its candidate OR to the owning '
    'employer org (multi-tenant).';
COMMENT ON POLICY comm_channels_org_write IS
    'Employers can INSERT/UPDATE only their own org''s communication channels.';

-- --- profile_versions: service_role full access ----------------------------
DROP POLICY IF EXISTS profile_versions_service_all ON public.profile_versions;
CREATE POLICY profile_versions_service_all
    ON public.profile_versions
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- --- profile_versions: visible to the candidate only -----------------------
DROP POLICY IF EXISTS profile_versions_candidate_select ON public.profile_versions;
CREATE POLICY profile_versions_candidate_select
    ON public.profile_versions
    FOR SELECT
    TO authenticated
    USING (public.current_candidate_id() = profile_versions.candidate_id);

COMMENT ON POLICY profile_versions_candidate_select IS
    'A candidate can SELECT only their own profile versions. Employer reads '
    'go through the backend service-role client against the pinned snapshot '
    'in recommendations.resume_snapshot.';

-- ===========================================================================
-- updated_at bump trigger for communication_channels (mirrors 061 convention)
-- ===========================================================================
CREATE OR REPLACE FUNCTION public.touch_comm_channel_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_comm_channels_updated_at ON public.communication_channels;
CREATE TRIGGER trg_comm_channels_updated_at
    BEFORE UPDATE ON public.communication_channels
    FOR EACH ROW
    EXECUTE FUNCTION public.touch_comm_channel_updated_at();

-- ===========================================================================
-- identity_status roll-up guard
--
-- Enforce the RULE that identity_status = 'verified' only when all three
-- document statuses are 'verified'. The backend is expected to set the
-- roll-up, but this trigger guarantees the invariant at the DB layer so it
-- can never be violated by a stray UPDATE.
-- ===========================================================================
CREATE OR REPLACE FUNCTION public.enforce_candidate_identity_rollup()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    all_verified BOOLEAN;
BEGIN
    all_verified := (
        COALESCE(NEW.id_card_status, 'pending') = 'verified'
        AND COALESCE(NEW.education_doc_status, 'pending') = 'verified'
        AND COALESCE(NEW.resume_status, 'pending') = 'verified'
    );

    IF all_verified AND NEW.identity_status <> 'verified' THEN
        NEW.identity_status := 'verified';
        IF NEW.identity_verified_at IS NULL THEN
            NEW.identity_verified_at := NOW();
        END IF;
    ELSIF NOT all_verified AND NEW.identity_status = 'verified' THEN
        -- cannot be verified if any document is not verified
        NEW.identity_status := 'submitted';
        NEW.identity_verified_at := NULL;
    END IF;

    IF NEW.identity_status = 'verified' AND NEW.identity_verified_at IS NULL THEN
        NEW.identity_verified_at := NOW();
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_candidate_identity_rollup ON public.candidates;
CREATE TRIGGER trg_candidate_identity_rollup
    BEFORE INSERT OR UPDATE OF identity_status, id_card_status,
                              education_doc_status, resume_status
    ON public.candidates
    FOR EACH ROW
    EXECUTE FUNCTION public.enforce_candidate_identity_rollup();

COMMENT ON FUNCTION public.enforce_candidate_identity_rollup() IS
    'v11.2 — guarantees identity_status=verified ONLY when id_card_status, '
    'education_doc_status and resume_status are all verified. Stamps '
    'identity_verified_at on transition to verified.';

COMMIT;
