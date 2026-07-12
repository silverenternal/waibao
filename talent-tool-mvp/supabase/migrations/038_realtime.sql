-- v6.0 T2201 — GPT-4o Realtime migration
-- Adds: realtime_sessions, realtime_transcripts, realtime_metrics tables.
-- A realtime_sessions row represents a single user-conversation WebSocket
-- connection to the OpenAI Realtime API.

-- ---------------------------------------------------------------------------
-- realtime_sessions — per user / conversation session metadata
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.realtime_sessions (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    conversation_id TEXT NOT NULL DEFAULT '',
    model           TEXT NOT NULL DEFAULT 'gpt-4o-realtime-preview',
    voice           TEXT NOT NULL DEFAULT 'alloy',
    status          TEXT NOT NULL DEFAULT 'created',  -- created|active|ended|error
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_realtime_sessions_user ON public.realtime_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_realtime_sessions_conversation ON public.realtime_sessions(conversation_id);
CREATE INDEX IF NOT EXISTS idx_realtime_sessions_status ON public.realtime_sessions(status);

COMMENT ON TABLE public.realtime_sessions IS
    'GPT-4o Realtime sessions: per-user, per-conversation WebSocket connections.';

-- ---------------------------------------------------------------------------
-- realtime_transcripts — per-turn transcript log
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.realtime_transcripts (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,                 -- user|assistant|function
    text        TEXT NOT NULL DEFAULT '',
    audio_bytes INTEGER NOT NULL DEFAULT 0,
    ts          DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_realtime_transcripts_session ON public.realtime_transcripts(session_id);
CREATE INDEX IF NOT EXISTS idx_realtime_transcripts_role ON public.realtime_transcripts(role);

COMMENT ON TABLE public.realtime_transcripts IS
    'Per-turn transcripts for realtime sessions (user / assistant / function).';

-- ---------------------------------------------------------------------------
-- realtime_metrics — live and final session metrics
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.realtime_metrics (
    session_id              TEXT PRIMARY KEY,
    first_audio_latency_ms  DOUBLE PRECISION,
    audio_input_chunks      INTEGER NOT NULL DEFAULT 0,
    audio_output_chunks     INTEGER NOT NULL DEFAULT 0,
    text_turns              INTEGER NOT NULL DEFAULT 0,
    function_calls          INTEGER NOT NULL DEFAULT 0,
    interruptions           INTEGER NOT NULL DEFAULT 0,
    input_tokens            INTEGER NOT NULL DEFAULT 0,
    output_tokens           INTEGER NOT NULL DEFAULT 0,
    audio_input_seconds     DOUBLE PRECISION NOT NULL DEFAULT 0,
    audio_output_seconds    DOUBLE PRECISION NOT NULL DEFAULT 0,
    total_tokens            INTEGER NOT NULL DEFAULT 0,
    duration_sec            DOUBLE PRECISION NOT NULL DEFAULT 0,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_realtime_metrics_updated ON public.realtime_metrics(updated_at);

COMMENT ON TABLE public.realtime_metrics IS
    'Live/final session metrics: latency, chunks, tokens, audio seconds, turns.';

-- ---------------------------------------------------------------------------
-- RLS (best-effort; service-role writes via api/deps.get_supabase_admin)
-- ---------------------------------------------------------------------------
ALTER TABLE public.realtime_sessions     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.realtime_transcripts  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.realtime_metrics      ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    PERFORM 1 FROM pg_policies WHERE schemaname='public' AND tablename='realtime_sessions' AND policyname='realtime_sessions_user_select';
EXCEPTION WHEN OTHERS THEN NULL; END $$;

DROP POLICY IF EXISTS realtime_sessions_user_select ON public.realtime_sessions;
CREATE POLICY realtime_sessions_user_select ON public.realtime_sessions
    FOR SELECT USING (auth.uid()::text = user_id);

DROP POLICY IF EXISTS realtime_sessions_user_insert ON public.realtime_sessions;
CREATE POLICY realtime_sessions_user_insert ON public.realtime_sessions
    FOR INSERT WITH CHECK (auth.uid()::text = user_id);

DROP POLICY IF EXISTS realtime_sessions_user_update ON public.realtime_sessions;
CREATE POLICY realtime_sessions_user_update ON public.realtime_sessions
    FOR UPDATE USING (auth.uid()::text = user_id);

DROP POLICY IF EXISTS realtime_transcripts_user_select ON public.realtime_transcripts;
CREATE POLICY realtime_transcripts_user_select ON public.realtime_transcripts
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.realtime_sessions s
            WHERE s.id = realtime_transcripts.session_id
              AND s.user_id = auth.uid()::text
        )
    );

DROP POLICY IF EXISTS realtime_metrics_user_select ON public.realtime_metrics;
CREATE POLICY realtime_metrics_user_select ON public.realtime_metrics
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.realtime_sessions s
            WHERE s.id = realtime_metrics.session_id
              AND s.user_id = auth.uid()::text
        )
    );
