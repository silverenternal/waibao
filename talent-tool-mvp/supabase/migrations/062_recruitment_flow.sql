-- v11.0 T6109 — Recruitment flow: contact logs + interview schedule.
--
-- Once a talent↔role recommendation has been pushed (T6104) the employer's
-- HR needs to track the downstream recruitment lifecycle:
--
--   * contact_logs      — every outreach attempt to a candidate (phone /
--     email / wechat / video), with method, outcome status and free-text
--     notes. One candidate can have many contact logs (the full outreach
--     history);
--   * interview_schedule — a booked interview slot for a candidate against
--     a role, with date / time / location / format (onsite / video / phone)
--     and a status that moves scheduled → completed → cancelled.
--
-- Both tables are org-scoped (multi-tenant via org_id + tenant_id) and sit
-- behind RLS so an authenticated employer only ever sees their own org's
-- recruitment funnel.
--
-- Access model (甲方合同要求):
--   * employer (client role, owns org_id)   → full CRUD on their org's
--     contact logs + interview schedule;
--   * platform admin                        → everything above for every org.

BEGIN;

-- ---------------------------------------------------------------------------
-- contact_logs — one row per outreach attempt to a candidate
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.contact_logs (
    id              BIGSERIAL PRIMARY KEY,
    candidate_id    TEXT NOT NULL,                 -- referenced talent id (recommendation.candidate_id)
    role_id         TEXT,                          -- optional: the role this outreach is about
    org_id          TEXT NOT NULL,                 -- employer org that owns this log
    tenant_id       UUID,                          -- v8.0 multi-tenant column (back-filled)

    hr_id           TEXT,                          -- the HR/recruiter user who made contact
    contact_method  TEXT NOT NULL DEFAULT 'phone'
                      CHECK (contact_method IN ('phone', 'email', 'wechat', 'sms', 'video', 'in_person', 'other')),
    contact_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    status          TEXT NOT NULL DEFAULT 'reached'
                      CHECK (status IN ('reached', 'no_answer', 'left_message', 'rejected', 'interested', 'follow_up')),
    notes           TEXT NOT NULL DEFAULT '',

    -- candidate denormalised for list display without a join
    candidate_name  TEXT NOT NULL DEFAULT '',
    role_title      TEXT NOT NULL DEFAULT '',

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contact_logs_org
    ON public.contact_logs(org_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_contact_logs_candidate
    ON public.contact_logs(candidate_id, contact_date DESC);

CREATE INDEX IF NOT EXISTS idx_contact_logs_role
    ON public.contact_logs(role_id);

CREATE INDEX IF NOT EXISTS idx_contact_logs_status
    ON public.contact_logs(org_id, status);

CREATE INDEX IF NOT EXISTS idx_contact_logs_tenant
    ON public.contact_logs(tenant_id);

COMMENT ON TABLE public.contact_logs IS
    'T6109 — one outreach attempt to a candidate. Org-scoped. A candidate '
    'accumulates many contact logs over the recruitment lifecycle.';

-- ---------------------------------------------------------------------------
-- interview_schedule — a booked interview slot for a candidate↔role
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.interview_schedule (
    id              BIGSERIAL PRIMARY KEY,
    candidate_id    TEXT NOT NULL,
    role_id         TEXT,                          -- optional: the role being interviewed for
    org_id          TEXT NOT NULL,                 -- employer org that owns this interview
    tenant_id       UUID,                          -- v8.0 multi-tenant column (back-filled)

    hr_id           TEXT,                          -- the HR/recruiter who booked the slot
    date            DATE NOT NULL,
    time            TEXT NOT NULL,                 -- "14:30" (HH:MM, 24h) — kept as text for tz-neutral display
    location        TEXT NOT NULL DEFAULT '',
    format          TEXT NOT NULL DEFAULT 'onsite'
                      CHECK (format IN ('onsite', 'video', 'phone')),
    status          TEXT NOT NULL DEFAULT 'scheduled'
                      CHECK (status IN ('scheduled', 'completed', 'cancelled', 'no_show', 'rescheduled')),

    -- candidate/role denormalised for kanban display without a join
    candidate_name  TEXT NOT NULL DEFAULT '',
    role_title      TEXT NOT NULL DEFAULT '',

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_interview_schedule_org
    ON public.interview_schedule(org_id, date DESC);

CREATE INDEX IF NOT EXISTS idx_interview_schedule_candidate
    ON public.interview_schedule(candidate_id, date DESC);

CREATE INDEX IF NOT EXISTS idx_interview_schedule_role
    ON public.interview_schedule(role_id);

CREATE INDEX IF NOT EXISTS idx_interview_schedule_status
    ON public.interview_schedule(org_id, status);

CREATE INDEX IF NOT EXISTS idx_interview_schedule_date
    ON public.interview_schedule(date);

CREATE INDEX IF NOT EXISTS idx_interview_schedule_tenant
    ON public.interview_schedule(tenant_id);

COMMENT ON TABLE public.interview_schedule IS
    'T6109 — a booked interview slot. Status lifecycle: scheduled → '
    'completed | cancelled | no_show | rescheduled.';

-- ---------------------------------------------------------------------------
-- Row Level Security
--
--   * service_role / platform admin: full access to every org (the FastAPI
--     backend reads/writes via the service-role admin client);
--   * authenticated employer: SELECT/INSERT/UPDATE only the rows whose
--     org_id matches the JWT claim ``raw_app_meta_data.org_id`` (or
--     ``user_metadata.org_id``).
-- ---------------------------------------------------------------------------
ALTER TABLE public.contact_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.interview_schedule ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS contact_logs_service_all ON public.contact_logs;
CREATE POLICY contact_logs_service_all ON public.contact_logs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS contact_logs_org_select ON public.contact_logs;
CREATE POLICY contact_logs_org_select ON public.contact_logs
    FOR SELECT TO authenticated USING (
        COALESCE(
            (raw_app_meta_data ->> 'org_id') = (contact_logs.org_id),
            (auth.jwt() -> 'user_metadata' ->> 'org_id') = (contact_logs.org_id)
        )
    );

DROP POLICY IF EXISTS contact_logs_org_write ON public.contact_logs;
CREATE POLICY contact_logs_org_write ON public.contact_logs
    FOR ALL TO authenticated USING (
        COALESCE(
            (raw_app_meta_data ->> 'org_id') = (contact_logs.org_id),
            (auth.jwt() -> 'user_metadata' ->> 'org_id') = (contact_logs.org_id)
        )
    ) WITH CHECK (
        COALESCE(
            (raw_app_meta_data ->> 'org_id') = (contact_logs.org_id),
            (auth.jwt() -> 'user_metadata' ->> 'org_id') = (contact_logs.org_id)
        )
    );

DROP POLICY IF EXISTS interview_schedule_service_all ON public.interview_schedule;
CREATE POLICY interview_schedule_service_all ON public.interview_schedule
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS interview_schedule_org_select ON public.interview_schedule;
CREATE POLICY interview_schedule_org_select ON public.interview_schedule
    FOR SELECT TO authenticated USING (
        COALESCE(
            (raw_app_meta_data ->> 'org_id') = (interview_schedule.org_id),
            (auth.jwt() -> 'user_metadata' ->> 'org_id') = (interview_schedule.org_id)
        )
    );

DROP POLICY IF EXISTS interview_schedule_org_write ON public.interview_schedule;
CREATE POLICY interview_schedule_org_write ON public.interview_schedule
    FOR ALL TO authenticated USING (
        COALESCE(
            (raw_app_meta_data ->> 'org_id') = (interview_schedule.org_id),
            (auth.jwt() -> 'user_metadata' ->> 'org_id') = (interview_schedule.org_id)
        )
    ) WITH CHECK (
        COALESCE(
            (raw_app_meta_data ->> 'org_id') = (interview_schedule.org_id),
            (auth.jwt() -> 'user_metadata' ->> 'org_id') = (interview_schedule.org_id)
        )
    );

COMMIT;
