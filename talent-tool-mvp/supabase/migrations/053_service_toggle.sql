-- v8.0 T3501 — Service Toggle Core
-- Adds: services (catalog), service_overrides (per-org override), service_audit (audit log)
--
-- Retention: 7 years (compliance requirement for regulated industries).
--
-- Layered access control (used by feature_access.check):
--   1. Global status (services.status)
--   2. Plan gate (services.plan_required)
--   3. Role gate (services.roles_allowed)
--   4. Per-org override (service_overrides) — highest priority
--
-- RLS:
--   * services            — everyone reads; only admins write
--   * service_overrides   — everyone reads; only admins write
--   * service_audit       — append-only everyone reads; admins write; never delete

BEGIN;

-- ---------------------------------------------------------------------------
-- services — catalog of every registered service
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.services (
    id               BIGSERIAL PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE
                       CHECK (char_length(name) BETWEEN 2 AND 64),
    display_name     TEXT NOT NULL
                       CHECK (char_length(display_name) BETWEEN 2 AND 128),
    description      TEXT NOT NULL DEFAULT ''
                       CHECK (char_length(description) <= 1024),
    category         TEXT NOT NULL DEFAULT 'misc'
                       CHECK (category IN (
                           'agent', 'api', 'business', 'integration',
                           'platform', 'frontend', 'analytics', 'misc'
                       )),
    status           TEXT NOT NULL DEFAULT 'enabled'
                       CHECK (status IN ('enabled', 'disabled', 'maintenance', 'beta')),
    plan_required    TEXT NOT NULL DEFAULT 'free'
                       CHECK (plan_required IN ('free', 'pro', 'enterprise', 'internal')),
    roles_allowed    JSONB NOT NULL DEFAULT '[]'::jsonb
                       CHECK (jsonb_typeof(roles_allowed) = 'array'),
    dependencies     JSONB NOT NULL DEFAULT '[]'::jsonb
                       CHECK (jsonb_typeof(dependencies) = 'array'),
    version          INTEGER NOT NULL DEFAULT 1,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by       TEXT
);

CREATE INDEX IF NOT EXISTS idx_services_status
    ON public.services(status);

CREATE INDEX IF NOT EXISTS idx_services_category
    ON public.services(category);

CREATE INDEX IF NOT EXISTS idx_services_plan
    ON public.services(plan_required);

COMMENT ON TABLE public.services IS
    'Service catalog. Each row is one addressable capability (agent, API, '
    'business module). Status controls global availability; plan_required '
    'and roles_allowed add layered gating; dependencies list upstream '
    'service names that must be enabled first.';

-- ---------------------------------------------------------------------------
-- service_overrides — per-org forced enable/disable (highest priority)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.service_overrides (
    id              BIGSERIAL PRIMARY KEY,
    org_id          TEXT NOT NULL,
    service_name    TEXT NOT NULL
                       CHECK (char_length(service_name) BETWEEN 2 AND 64),
    override_status TEXT NOT NULL
                       CHECK (override_status IN ('enabled', 'disabled', 'maintenance')),
    reason          TEXT NOT NULL DEFAULT ''
                       CHECK (char_length(reason) <= 512),
    expires_at      TIMESTAMPTZ,
    created_by      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_service_overrides_org
    ON public.service_overrides(org_id, service_name);

CREATE INDEX IF NOT EXISTS idx_service_overrides_name
    ON public.service_overrides(service_name);

CREATE UNIQUE INDEX IF NOT EXISTS uq_service_overrides_org_name
    ON public.service_overrides(org_id, service_name);

COMMENT ON TABLE public.service_overrides IS
    'Per-org service override. Highest priority in the access check: '
    'if a row exists for (org_id, service_name) and not expired, it '
    'forces the override_status regardless of the global status / plan / role.';

-- ---------------------------------------------------------------------------
-- service_audit — 7-year retained change log
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.service_audit (
    id            BIGSERIAL PRIMARY KEY,
    service_name  TEXT NOT NULL
                     CHECK (char_length(service_name) BETWEEN 2 AND 64),
    action        TEXT NOT NULL
                     CHECK (action IN ('enable', 'disable', 'override', 'rollback', 'register', 'deregister')),
    actor_id      TEXT,
    reason        TEXT NOT NULL DEFAULT '',
    before        JSONB,
    after         JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_service_audit_name
    ON public.service_audit(service_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_service_audit_actor
    ON public.service_audit(actor_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_service_audit_created
    ON public.service_audit(created_at DESC);

COMMENT ON TABLE public.service_audit IS
    'Append-only audit trail for service toggle mutations. Retained 7 years '
    'for compliance. Never DELETE — only INSERT.';

-- ---------------------------------------------------------------------------
-- 7-year retention trigger
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.service_audit_enforce_retention()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    -- hard refuse any DELETE on service_audit (compliance: 7-year retention)
    IF (TG_OP = 'DELETE') THEN
        RAISE EXCEPTION 'service_audit rows must be retained for 7 years; DELETE forbidden';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_service_audit_retention ON public.service_audit;
CREATE TRIGGER trg_service_audit_retention
    BEFORE DELETE ON public.service_audit
    FOR EACH ROW
    EXECUTE FUNCTION public.service_audit_enforce_retention();

-- ---------------------------------------------------------------------------
-- updated_at trigger for services
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.services_touch_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_services_touch_updated_at ON public.services;
CREATE TRIGGER trg_services_touch_updated_at
    BEFORE UPDATE ON public.services
    FOR EACH ROW
    EXECUTE FUNCTION public.services_touch_updated_at();

-- ---------------------------------------------------------------------------
-- RLS policies
-- ---------------------------------------------------------------------------
ALTER TABLE public.services ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.service_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.service_audit ENABLE ROW LEVEL SECURITY;

-- services: everyone reads
DROP POLICY IF EXISTS services_read ON public.services;
CREATE POLICY services_read ON public.services
    FOR SELECT USING (TRUE);

-- services: admins write (we use the "admin" role stored in users.role)
DROP POLICY IF EXISTS services_admin_write ON public.services;
CREATE POLICY services_admin_write ON public.services
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.users u
            WHERE u.id = auth.uid() AND u.role = 'admin'
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.users u
            WHERE u.id = auth.uid() AND u.role = 'admin'
        )
    );

-- service_overrides: everyone reads
DROP POLICY IF EXISTS service_overrides_read ON public.service_overrides;
CREATE POLICY service_overrides_read ON public.service_overrides
    FOR SELECT USING (TRUE);

-- service_overrides: admins write
DROP POLICY IF EXISTS service_overrides_admin_write ON public.service_overrides;
CREATE POLICY service_overrides_admin_write ON public.service_overrides
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.users u
            WHERE u.id = auth.uid() AND u.role = 'admin'
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.users u
            WHERE u.id = auth.uid() AND u.role = 'admin'
        )
    );

-- service_audit: everyone reads; admins write; nobody deletes (trigger)
DROP POLICY IF EXISTS service_audit_read ON public.service_audit;
CREATE POLICY service_audit_read ON public.service_audit
    FOR SELECT USING (TRUE);

DROP POLICY IF EXISTS service_audit_admin_insert ON public.service_audit;
CREATE POLICY service_audit_admin_insert ON public.service_audit
    FOR INSERT WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.users u
            WHERE u.id = auth.uid() AND u.role = 'admin'
        )
        OR auth.role() = 'service_role'  -- backend service_role writes too
    );

-- ---------------------------------------------------------------------------
-- Service-role bypass note
--   The FastAPI service uses service_role key for back-end writes, which
--   bypasses RLS. The policies above protect front-end / direct DB clients.
-- ---------------------------------------------------------------------------

COMMIT;
