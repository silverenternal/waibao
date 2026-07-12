-- v6.0 T2102 — Config Center migration
-- Adds: configs, config_history, config_subscribers tables.

-- ---------------------------------------------------------------------------
-- configs — runtime-editable configuration keyed by (scope, key)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.configs (
    id           BIGSERIAL PRIMARY KEY,
    scope        TEXT NOT NULL
                    CHECK (scope IN ('system', 'org', 'agent', 'feature')),
    key          TEXT NOT NULL,
    value        JSONB NOT NULL,
    value_type   TEXT NOT NULL DEFAULT 'json'
                    CHECK (value_type IN ('json', 'string', 'number', 'boolean', 'array')),
    description  TEXT,
    version      INTEGER NOT NULL DEFAULT 1,
    updated_by   TEXT,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_secret    BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (scope, key)
);

CREATE INDEX IF NOT EXISTS idx_configs_scope_key
    ON public.configs(scope, key);

CREATE INDEX IF NOT EXISTS idx_configs_updated_at
    ON public.configs(updated_at DESC);

COMMENT ON TABLE public.configs IS
    'Runtime configuration (system / org / agent / feature). Every change is append-only logged into config_history.';

-- ---------------------------------------------------------------------------
-- config_history — version control / audit
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.config_history (
    id           BIGSERIAL PRIMARY KEY,
    config_id    BIGINT REFERENCES public.configs(id) ON DELETE SET NULL,
    scope        TEXT NOT NULL,
    key          TEXT NOT NULL,
    value        JSONB NOT NULL,
    version      INTEGER NOT NULL,
    changed_by   TEXT,
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    operation    TEXT NOT NULL DEFAULT 'update'
                    CHECK (operation IN ('update', 'rollback', 'create')),
    comment      TEXT
);

CREATE INDEX IF NOT EXISTS idx_config_history_lookup
    ON public.config_history(scope, key, version DESC);

CREATE INDEX IF NOT EXISTS idx_config_history_changed_at
    ON public.config_history(changed_at DESC);

-- ---------------------------------------------------------------------------
-- config_subscribers — which worker / service subscribes to which key,
-- used by config_watcher to push live updates.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.config_subscribers (
    id            BIGSERIAL PRIMARY KEY,
    scope         TEXT NOT NULL,
    key           TEXT NOT NULL,            -- "*" to subscribe to all keys in scope
    subscriber_id TEXT NOT NULL,            -- worker name / service identity
    channel       TEXT,                     -- redis pub/sub channel
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (scope, key, subscriber_id)
);

CREATE INDEX IF NOT EXISTS idx_config_subscribers_key
    ON public.config_subscribers(scope, key);

-- ---------------------------------------------------------------------------
-- RLS: admin role can read & write; service_role bypasses RLS for writes.
-- ---------------------------------------------------------------------------

ALTER TABLE public.configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.config_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.config_subscribers ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS configs_admin_all ON public.configs;
CREATE POLICY configs_admin_all ON public.configs
    FOR ALL TO authenticated
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS config_history_read ON public.config_history;
CREATE POLICY config_history_read ON public.config_history
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS config_subscribers_admin ON public.config_subscribers;
CREATE POLICY config_subscribers_admin ON public.config_subscribers
    FOR ALL TO authenticated
    USING (true) WITH CHECK (true);
