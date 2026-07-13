-- v7.0 T3003 — White-label + Private-deployment branding
-- Adds: tenant_branding (one row per tenant) + tenant_branding_audit.
--
-- The frontend reads tenant_branding via /v1/branding/{tenant_id} and
-- pushes the values into CSS variables (see frontend/lib/theme.ts and
-- components/WhiteLabelProvider.tsx).  Email + PDF rendering use the
-- same row so transactional mail and weekly reports look like the
-- customer's product, not Waibao's.
--
-- RLS:
--   * tenant_members can read their own row
--   * tenant_admins can write their own row
--   * service_role bypasses RLS for the FastAPI service
--
-- The frontend / SDK reads via service-role on the API, so the public
-- SELECT policy exists mainly for direct Supabase clients in
-- self-hosted deployments.

BEGIN;

-- ---------------------------------------------------------------------------
-- tenant_branding — one row per tenant
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.tenant_branding (
    tenant_id         TEXT PRIMARY KEY,
    product_name      TEXT NOT NULL DEFAULT 'Waibao Recruitment'
                       CHECK (char_length(product_name) BETWEEN 2 AND 64),
    domain            TEXT NOT NULL DEFAULT '',
    logo_url          TEXT NOT NULL DEFAULT '',
    favicon_url       TEXT NOT NULL DEFAULT '',
    primary_color     TEXT NOT NULL DEFAULT '#2563EB'
                       CHECK (primary_color ~ '^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$'),
    secondary_color   TEXT NOT NULL DEFAULT '#0F172A'
                       CHECK (secondary_color ~ '^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$'),
    accent_color      TEXT NOT NULL DEFAULT '#F59E0B'
                       CHECK (accent_color ~ '^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$'),
    font_family       TEXT NOT NULL DEFAULT 'Inter'
                       CHECK (char_length(font_family) BETWEEN 2 AND 64),
    support_email     TEXT NOT NULL DEFAULT 'support@waibao.example.com',
    footer_text       TEXT NOT NULL DEFAULT 'Powered by Waibao Recruitment'
                       CHECK (char_length(footer_text) <= 512),
    locale            TEXT NOT NULL DEFAULT 'zh-CN'
                       CHECK (locale IN ('zh-CN', 'en-US', 'ja-JP')),
    email_template    TEXT NOT NULL DEFAULT 'transactional'
                       CHECK (email_template IN (
                           'transactional', 'marketing', 'report',
                           'interview_invite', 'offer_letter'
                       )),
    report_template   TEXT NOT NULL DEFAULT 'default'
                       CHECK (report_template ~ '^[a-z0-9_\-]{1,32}$'),
    custom_css        TEXT NOT NULL DEFAULT ''
                       CHECK (char_length(custom_css) <= 8192),
    hide_powered_by   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by        TEXT
);

CREATE INDEX IF NOT EXISTS idx_tenant_branding_domain
    ON public.tenant_branding(domain)
    WHERE domain <> '';

COMMENT ON TABLE public.tenant_branding IS
    'Per-tenant white-label branding. Read by WhiteLabelProvider at runtime '
    'and consumed by email + PDF renderers. One row per tenant.';

-- ---------------------------------------------------------------------------
-- tenant_branding_audit — change log
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.tenant_branding_audit (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    action      TEXT NOT NULL CHECK (action IN ('updated', 'deleted', 'created')),
    actor       TEXT,
    diff        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenant_branding_audit_tenant
    ON public.tenant_branding_audit(tenant_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- updated_at trigger
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.tg_set_updated_at_tenant_branding()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tenant_branding_updated ON public.tenant_branding;
CREATE TRIGGER trg_tenant_branding_updated
    BEFORE UPDATE ON public.tenant_branding
    FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at_tenant_branding();

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
ALTER TABLE public.tenant_branding       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tenant_branding_audit ENABLE ROW LEVEL SECURITY;

-- Public read (used by direct Supabase clients in self-hosted deployments).
DROP POLICY IF EXISTS tenant_branding_public_read ON public.tenant_branding;
CREATE POLICY tenant_branding_public_read ON public.tenant_branding
    FOR SELECT TO anon, authenticated
    USING (true);

-- Tenant-admin write. In a real deployment this would check a
-- tenant_admins membership table; here we use the JWT 'tenant_id'
-- claim plus an 'is_admin' claim.  Self-hosted deployments that
-- don't use Supabase Auth just disable RLS via service-role.
DROP POLICY IF EXISTS tenant_branding_admin_write ON public.tenant_branding;
CREATE POLICY tenant_branding_admin_write ON public.tenant_branding
    FOR ALL TO authenticated
    USING (
        (auth.jwt() ->> 'tenant_id') = tenant_id
        AND coalesce((auth.jwt() ->> 'is_admin')::boolean, false)
    )
    WITH CHECK (
        (auth.jwt() ->> 'tenant_id') = tenant_id
    );

-- Service-role bypass for the FastAPI server.
DROP POLICY IF EXISTS tenant_branding_service ON public.tenant_branding;
CREATE POLICY tenant_branding_service ON public.tenant_branding
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS tenant_branding_audit_service ON public.tenant_branding_audit;
CREATE POLICY tenant_branding_audit_service ON public.tenant_branding_audit
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ---------------------------------------------------------------------------
-- Seed: a single default row for the public SaaS tenant so the API
-- always returns *something* on cache miss.
-- ---------------------------------------------------------------------------
INSERT INTO public.tenant_branding (tenant_id, product_name, domain)
VALUES ('public', 'Waibao Recruitment', '')
ON CONFLICT (tenant_id) DO NOTHING;

COMMIT;