-- ============================================================
-- Migration 029: ATS Bidirectional Sync (T1501)
--   - ats_integrations: integration config (Greenhouse / Lever / ...)
--   - ats_sync_log: every sync run with diff details
--   - ats_conflicts: record conflicts produced during sync
-- ============================================================

-- ------------------------------------------------------------
-- 1) ats_integrations
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ats_integrations (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID,                                  -- optional multi-tenant
    provider                VARCHAR(32)  NOT NULL,                 -- 'greenhouse' | 'lever' | 'mock_ats' | ...
    display_name            VARCHAR(128) NOT NULL,
    api_key_secret          TEXT,                                  -- encrypted via pgcrypto (Supabase vault)
    api_base_url            TEXT,
    default_owner_external  VARCHAR(128),
    extra_config            JSONB NOT NULL DEFAULT '{}'::JSONB,
    active                  BOOLEAN NOT NULL DEFAULT TRUE,
    last_synced_at          TIMESTAMPTZ,
    last_status             VARCHAR(16),                           -- ok / error / partial / never
    last_error              TEXT,
    created_by              UUID,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, provider, display_name)
);

CREATE INDEX IF NOT EXISTS idx_ats_integrations_tenant ON ats_integrations(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ats_integrations_provider ON ats_integrations(provider);
CREATE INDEX IF NOT EXISTS idx_ats_integrations_active ON ats_integrations(active);

-- ------------------------------------------------------------
-- 2) ats_sync_log
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ats_sync_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    integration_id      UUID NOT NULL REFERENCES ats_integrations(id) ON DELETE CASCADE,
    sync_type           VARCHAR(16) NOT NULL,                -- 'candidates' | 'jobs' | 'both'
    direction           VARCHAR(8)  NOT NULL,                -- 'pull' | 'push' | 'two_way'
    triggered_by        VARCHAR(32) NOT NULL DEFAULT 'scheduler',  -- 'scheduler' | 'manual' | 'webhook'
    status              VARCHAR(16) NOT NULL,                -- 'ok' | 'partial' | 'failed'
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at         TIMESTAMPTZ,
    duration_ms         INTEGER,
    total               INTEGER NOT NULL DEFAULT 0,
    succeeded           INTEGER NOT NULL DEFAULT 0,
    failed              INTEGER NOT NULL DEFAULT 0,
    conflicts           INTEGER NOT NULL DEFAULT 0,
    diff                JSONB NOT NULL DEFAULT '[]'::JSONB,    -- per-record diff
    error               TEXT
);

CREATE INDEX IF NOT EXISTS idx_ats_sync_log_integration ON ats_sync_log(integration_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_ats_sync_log_status ON ats_sync_log(status);

-- ------------------------------------------------------------
-- 3) ats_conflicts
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ats_conflicts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    integration_id      UUID NOT NULL REFERENCES ats_integrations(id) ON DELETE CASCADE,
    sync_log_id         UUID REFERENCES ats_sync_log(id) ON DELETE SET NULL,
    entity_type         VARCHAR(16) NOT NULL,                -- 'candidate' | 'job'
    local_id            UUID,
    external_id         VARCHAR(128) NOT NULL,
    field_diffs         JSONB NOT NULL DEFAULT '[]'::JSONB,  -- [{field, local, external, decision}]
    resolution          VARCHAR(32),                         -- 'auto_merged' | 'manual_pending' | 'local_wins' | 'remote_wins'
    resolved_by         UUID,
    resolved_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ats_conflicts_integration ON ats_conflicts(integration_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ats_conflicts_unresolved ON ats_conflicts(integration_id) WHERE resolution IS NULL;

-- ------------------------------------------------------------
-- updated_at trigger
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_ats_integrations_touch()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tg_ats_integrations_touch ON ats_integrations;
CREATE TRIGGER tg_ats_integrations_touch
    BEFORE UPDATE ON ats_integrations
    FOR EACH ROW EXECUTE FUNCTION trg_ats_integrations_touch();

-- ------------------------------------------------------------
-- RLS
-- ------------------------------------------------------------
ALTER TABLE ats_integrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE ats_sync_log    ENABLE ROW LEVEL SECURITY;
ALTER TABLE ats_conflicts   ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ats_integrations_svc ON ats_integrations;
CREATE POLICY ats_integrations_svc ON ats_integrations FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS ats_sync_log_svc ON ats_sync_log;
CREATE POLICY ats_sync_log_svc ON ats_sync_log FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS ats_conflicts_svc ON ats_conflicts;
CREATE POLICY ats_conflicts_svc ON ats_conflicts FOR ALL TO service_role USING (true) WITH CHECK (true);
