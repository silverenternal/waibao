-- v6.0 T2103 — Feature Flags migration
-- Adds: feature_flags, feature_flag_overrides, feature_flag_audit tables.

-- ---------------------------------------------------------------------------
-- feature_flags — flag definitions, rollout rules and enabled switch
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.feature_flags (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    description     TEXT NOT NULL DEFAULT '',
    rules           JSONB NOT NULL DEFAULT '{}'::jsonb,
    rollout_percent INTEGER NOT NULL DEFAULT 0
                        CHECK (rollout_percent BETWEEN 0 AND 100),
    enabled         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by      TEXT
);

CREATE INDEX IF NOT EXISTS idx_feature_flags_enabled
    ON public.feature_flags(enabled);

COMMENT ON TABLE public.feature_flags IS
    'Feature flags: name, rollout percent, enabled switch and JSON rules '
    '(whitelist / blacklist / cohort gating).';

-- ---------------------------------------------------------------------------
-- feature_flag_overrides — forced enable/disable per (user_id, org_id, flag)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.feature_flag_overrides (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT,
    org_id      TEXT,
    flag_name   TEXT NOT NULL,
    value       BOOLEAN NOT NULL,
    reason      TEXT NOT NULL DEFAULT '',
    expires_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by  TEXT,
    CHECK (user_id IS NOT NULL OR org_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_ff_overrides_user
    ON public.feature_flag_overrides(user_id, flag_name);

CREATE INDEX IF NOT EXISTS idx_ff_overrides_org
    ON public.feature_flag_overrides(org_id, flag_name);

CREATE INDEX IF NOT EXISTS idx_ff_overrides_flag
    ON public.feature_flag_overrides(flag_name);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ff_overrides_user_flag
    ON public.feature_flag_overrides(flag_name, user_id)
    WHERE user_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_ff_overrides_org_flag
    ON public.feature_flag_overrides(flag_name, org_id)
    WHERE org_id IS NOT NULL;

COMMENT ON TABLE public.feature_flag_overrides IS
    'Per-user / per-org force-on / force-off overrides. Whitelist (value=true) '
    'takes precedence over blacklist (value=false). Always wins over rollout.';

-- ---------------------------------------------------------------------------
-- feature_flag_audit — append-only history of operator changes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.feature_flag_audit (
    id           BIGSERIAL PRIMARY KEY,
    flag_name    TEXT NOT NULL,
    action       TEXT NOT NULL
                    CHECK (action IN ('create', 'update', 'delete', 'override_set', 'override_remove')),
    before       JSONB,
    after        JSONB,
    actor        TEXT,
    note         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ff_audit_flag_name
    ON public.feature_flag_audit(flag_name, created_at DESC);

COMMENT ON TABLE public.feature_flag_audit IS
    'Append-only audit trail for feature flag changes — used by SOC2 / compliance.';

-- ---------------------------------------------------------------------------
-- Seed — bootstrap the five load-bearing v6.0 flags at 0% rollout
-- ---------------------------------------------------------------------------
INSERT INTO public.feature_flags (name, description, rollout_percent, enabled)
VALUES
    ('realtime_voice',    'Real-time voice interview streaming',  0, FALSE),
    ('ai_interview',      'AI-driven interview agent',           0, FALSE),
    ('video_resume',      'Video resume upload + transcript',    0, FALSE),
    ('ablation_study',    'Internal ablation study instrumentation', 0, FALSE),
    ('new_matching_v3',   'Next-generation matching engine v3',  0, FALSE)
ON CONFLICT (name) DO NOTHING;