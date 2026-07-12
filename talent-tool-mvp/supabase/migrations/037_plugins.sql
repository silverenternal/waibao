-- v6.0 T2104 — Plugin SDK migration
-- Adds: installed_plugins + plugin_runs + plugin_audit tables.

-- ---------------------------------------------------------------------------
-- installed_plugins — persistent catalogue of plugins and their state
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.installed_plugins (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    version         TEXT NOT NULL,
    manifest        JSONB NOT NULL,
    source_path     TEXT NOT NULL,
    state           TEXT NOT NULL DEFAULT 'installed'
                        CHECK (state IN ('installed', 'enabled', 'disabled', 'error')),
    enabled_at      TIMESTAMPTZ,
    installed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    installed_by    TEXT,
    last_run_at     TIMESTAMPTZ,
    last_run_status TEXT,
    run_count       INTEGER NOT NULL DEFAULT 0,
    failure_count   INTEGER NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_installed_plugins_state
    ON public.installed_plugins(state);

CREATE INDEX IF NOT EXISTS idx_installed_plugins_updated_at
    ON public.installed_plugins(updated_at DESC);

COMMENT ON TABLE public.installed_plugins IS
    'Persistent catalogue of installed plugins. State transitions are append-only '
    'logged into plugin_audit; the run history lives in plugin_runs.';

-- ---------------------------------------------------------------------------
-- plugin_runs — per-invocation record
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.plugin_runs (
    id            BIGSERIAL PRIMARY KEY,
    plugin_name   TEXT NOT NULL,
    status        TEXT NOT NULL
                    CHECK (status IN ('success', 'crash', 'permission', 'timeout', 'sandbox')),
    duration_ms   NUMERIC NOT NULL DEFAULT 0,
    error         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata      JSONB
);

CREATE INDEX IF NOT EXISTS idx_plugin_runs_name_time
    ON public.plugin_runs(plugin_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_plugin_runs_status
    ON public.plugin_runs(status);

COMMENT ON TABLE public.plugin_runs IS
    'Per-invocation history of plugin executions. Used for diagnostics and to '
    'detect flaky / unsafe plugins before they ship widely.';

-- ---------------------------------------------------------------------------
-- plugin_audit — append-only state-transition log
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.plugin_audit (
    id          BIGSERIAL PRIMARY KEY,
    plugin_name TEXT NOT NULL,
    action      TEXT NOT NULL
                  CHECK (action IN ('install', 'uninstall', 'enable', 'disable', 'run', 'error')),
    actor       TEXT,
    detail      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_plugin_audit_name_time
    ON public.plugin_audit(plugin_name, created_at DESC);

COMMENT ON TABLE public.plugin_audit IS
    'Append-only audit trail for plugin lifecycle changes. SOC2-relevant.';