-- v6.0 T2202 — AI Interview v2 migration
-- Adds: ai_interviews_v2, ai_interview_answers_v2, ai_interview_reports_v2 tables.
-- A v2 interview has a fixed 5-stage flow and a chosen persona.

-- ---------------------------------------------------------------------------
-- ai_interviews_v2 — interview sessions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ai_interviews_v2 (
    id                TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL,
    role              TEXT NOT NULL,
    role_label        TEXT NOT NULL DEFAULT '',
    difficulty        TEXT NOT NULL DEFAULT 'mid',
    persona_id        TEXT NOT NULL DEFAULT 'friendly_warm',
    persona_label     TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'in_progress',  -- in_progress|completed|abandoned
    realtime          BOOLEAN NOT NULL DEFAULT FALSE,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at       TIMESTAMPTZ,
    total_questions   INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_ai_interviews_v2_user ON public.ai_interviews_v2(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_interviews_v2_persona ON public.ai_interviews_v2(persona_id);
CREATE INDEX IF NOT EXISTS idx_ai_interviews_v2_status ON public.ai_interviews_v2(status);

COMMENT ON TABLE public.ai_interviews_v2 IS
    'AI Interview v2: 5-stage persona-driven sessions.';

-- ---------------------------------------------------------------------------
-- ai_interview_answers_v2 — per-question answers
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ai_interview_answers_v2 (
    interview_id      TEXT NOT NULL,
    question_id       TEXT NOT NULL,
    stage             TEXT NOT NULL DEFAULT '',
    transcript        TEXT NOT NULL DEFAULT '',
    duration_sec      DOUBLE PRECISION NOT NULL DEFAULT 0,
    follow_ups        INTEGER NOT NULL DEFAULT 0,
    depth_score       DOUBLE PRECISION NOT NULL DEFAULT 0,
    coverage_signals  JSONB NOT NULL DEFAULT '[]'::jsonb,
    evaluation        JSONB NOT NULL DEFAULT '{}'::jsonb,
    feedback          TEXT NOT NULL DEFAULT '',
    strengths         JSONB NOT NULL DEFAULT '[]'::jsonb,
    improvements      JSONB NOT NULL DEFAULT '[]'::jsonb,
    ts                DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (interview_id, question_id)
);

CREATE INDEX IF NOT EXISTS idx_ai_interview_answers_v2_interview ON public.ai_interview_answers_v2(interview_id);
CREATE INDEX IF NOT EXISTS idx_ai_interview_answers_v2_stage ON public.ai_interview_answers_v2(stage);

COMMENT ON TABLE public.ai_interview_answers_v2 IS
    'Per-question answers and evaluations for AI Interview v2.';

-- ---------------------------------------------------------------------------
-- ai_interview_reports_v2 — final aggregated reports
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ai_interview_reports_v2 (
    interview_id      TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL,
    role              TEXT NOT NULL DEFAULT '',
    persona_id        TEXT NOT NULL DEFAULT '',
    report            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_interview_reports_v2_user ON public.ai_interview_reports_v2(user_id);

COMMENT ON TABLE public.ai_interview_reports_v2 IS
    'Final aggregated reports with 5-dimension radar + commentary.';

-- ---------------------------------------------------------------------------
-- RLS (best-effort; service-role writes via api/deps.get_supabase_admin)
-- ---------------------------------------------------------------------------
ALTER TABLE public.ai_interviews_v2         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_interview_answers_v2  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_interview_reports_v2  ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ai_interviews_v2_user_select ON public.ai_interviews_v2;
CREATE POLICY ai_interviews_v2_user_select ON public.ai_interviews_v2
    FOR SELECT USING (auth.uid()::text = user_id);

DROP POLICY IF EXISTS ai_interviews_v2_user_insert ON public.ai_interviews_v2;
CREATE POLICY ai_interviews_v2_user_insert ON public.ai_interviews_v2
    FOR INSERT WITH CHECK (auth.uid()::text = user_id);

DROP POLICY IF EXISTS ai_interviews_v2_user_update ON public.ai_interviews_v2;
CREATE POLICY ai_interviews_v2_user_update ON public.ai_interviews_v2
    FOR UPDATE USING (auth.uid()::text = user_id);

DROP POLICY IF EXISTS ai_interview_answers_v2_user_select ON public.ai_interview_answers_v2;
CREATE POLICY ai_interview_answers_v2_user_select ON public.ai_interview_answers_v2
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.ai_interviews_v2 i
            WHERE i.id = ai_interview_answers_v2.interview_id
              AND i.user_id = auth.uid()::text
        )
    );

DROP POLICY IF EXISTS ai_interview_reports_v2_user_select ON public.ai_interview_reports_v2;
CREATE POLICY ai_interview_reports_v2_user_select ON public.ai_interview_reports_v2
    FOR SELECT USING (auth.uid()::text = user_id);
