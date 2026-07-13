-- v7.0 T2903 — Third-party Application Marketplace (Strapi-backed)
-- Adds: marketplace_plugins + plugin_releases + plugin_purchases
--       + plugin_reviews + plugin_downloads + plugin_audit tables.
--
-- The marketplace is the public face of the v6.0 Plugin SDK
-- (see supabase/migrations/037_plugins.sql + backend/services/plugins/sdk).
-- Authors publish *listings*; tenants install/uninstall *releases*.
-- Purchases are tracked separately so we can later plug in Stripe /
-- WeChat Pay revenue splits without rewriting the schema.
--
-- Note: we still keep this in Supabase (in addition to the Strapi
-- admin UI) so that the FastAPI side can read listings with RLS
-- without crossing the network boundary on the hot path.

BEGIN;

-- ---------------------------------------------------------------------------
-- marketplace_plugins — public listing (one per app)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.marketplace_plugins (
    id              BIGSERIAL PRIMARY KEY,
    slug            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    tagline         TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',
    category        TEXT NOT NULL DEFAULT 'integration'
                      CHECK (category IN (
                          'integration',        -- 钉钉/飞书/企业微信 集成
                          'analytics',          -- 漏斗/BI/报表
                          'automation',         -- 工作流/规则/A-B
                          'sourcing',           -- 主动寻才/AI sourcing
                          'assessment',         -- 测评/背景调查
                          'video',              -- 视频面试/简历
                          'utility',            -- 工具类
                          'other'
                      )),
    tags            TEXT[] NOT NULL DEFAULT '{}',
    author_id       TEXT NOT NULL,           -- developer app id (T2902)
    author_name     TEXT NOT NULL,
    author_email    TEXT,
    homepage_url    TEXT,
    repo_url        TEXT,
    icon_url        TEXT,
    screenshots     TEXT[] NOT NULL DEFAULT '{}',
    pricing_model   TEXT NOT NULL DEFAULT 'free'
                      CHECK (pricing_model IN ('free', 'one_time', 'subscription', 'usage')),
    price_cents     INTEGER NOT NULL DEFAULT 0,   -- in cents (USD) — 0 for free
    revenue_share   NUMERIC(5,4) NOT NULL DEFAULT 0.7000, -- 70% to author
    status          TEXT NOT NULL DEFAULT 'pending_review'
                      CHECK (status IN (
                          'pending_review', 'rejected', 'approved', 'deprecated', 'suspended'
                      )),
    rejection_reason TEXT,
    reviewed_by     TEXT,
    reviewed_at     TIMESTAMPTZ,
    total_installs  BIGINT NOT NULL DEFAULT 0,
    avg_rating      NUMERIC(3,2) NOT NULL DEFAULT 0.00,
    rating_count    INTEGER NOT NULL DEFAULT 0,
    manifest        JSONB NOT NULL DEFAULT '{}'::jsonb,   -- plugin.yaml content
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_marketplace_plugins_status
    ON public.marketplace_plugins(status);

CREATE INDEX IF NOT EXISTS idx_marketplace_plugins_category
    ON public.marketplace_plugins(category);

CREATE INDEX IF NOT EXISTS idx_marketplace_plugins_author
    ON public.marketplace_plugins(author_id);

CREATE INDEX IF NOT EXISTS idx_marketplace_plugins_installs
    ON public.marketplace_plugins(total_installs DESC);

CREATE INDEX IF NOT EXISTS idx_marketplace_plugins_rating
    ON public.marketplace_plugins(avg_rating DESC, rating_count DESC);

-- full-text-ish search via trigram (extension optional; pgcrypto provides digest
-- for slug hashing but the index below only requires the column to be text).
CREATE INDEX IF NOT EXISTS idx_marketplace_plugins_name_trgm
    ON public.marketplace_plugins USING gin (name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_marketplace_plugins_tags
    ON public.marketplace_plugins USING gin (tags);

COMMENT ON TABLE public.marketplace_plugins IS
    'Public marketplace listing. One row per app. The actual install state is '
    'recorded in installed_plugins (T2104) per tenant; this row is the catalog.';

-- ---------------------------------------------------------------------------
-- plugin_releases — semver versioned releases of an app
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.plugin_releases (
    id              BIGSERIAL PRIMARY KEY,
    plugin_id       BIGINT NOT NULL REFERENCES public.marketplace_plugins(id) ON DELETE CASCADE,
    version         TEXT NOT NULL,
    changelog       TEXT NOT NULL DEFAULT '',
    artifact_url    TEXT NOT NULL,        -- tarball/zip/Wheel
    artifact_sha256 TEXT NOT NULL,
    min_waibao_ver  TEXT NOT NULL DEFAULT '6.0.0',
    max_waibao_ver  TEXT,
    manifest        JSONB NOT NULL DEFAULT '{}'::jsonb,
    status          TEXT NOT NULL DEFAULT 'pending_review'
                      CHECK (status IN ('pending_review', 'approved', 'rejected', 'yanked')),
    size_bytes      BIGINT NOT NULL DEFAULT 0,
    downloads       BIGINT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (plugin_id, version)
);

CREATE INDEX IF NOT EXISTS idx_plugin_releases_plugin
    ON public.plugin_releases(plugin_id);

CREATE INDEX IF NOT EXISTS idx_plugin_releases_status
    ON public.plugin_releases(status);

COMMENT ON TABLE public.plugin_releases IS
    'Versioned releases. (plugin_id, version) is unique. Downloads are '
    'incremented atomically; tally rolls up to marketplace_plugins.';

-- ---------------------------------------------------------------------------
-- plugin_reviews — public ratings + comments
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.plugin_reviews (
    id          BIGSERIAL PRIMARY KEY,
    plugin_id   BIGINT NOT NULL REFERENCES public.marketplace_plugins(id) ON DELETE CASCADE,
    author_id   TEXT NOT NULL,    -- tenant_id or user_id
    author_name TEXT NOT NULL,
    rating      SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    title       TEXT NOT NULL DEFAULT '',
    body        TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'published'
                  CHECK (status IN ('published', 'hidden', 'flagged')),
    helpful_count INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_plugin_reviews_plugin
    ON public.plugin_reviews(plugin_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_plugin_reviews_author
    ON public.plugin_reviews(author_id);

COMMENT ON TABLE public.plugin_reviews IS
    'Public user reviews for marketplace plugins. One author can review the '
    'same plugin at most once; that constraint is enforced in service code.';

-- ---------------------------------------------------------------------------
-- plugin_downloads — per-installation record
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.plugin_downloads (
    id          BIGSERIAL PRIMARY KEY,
    plugin_id   BIGINT NOT NULL REFERENCES public.marketplace_plugins(id) ON DELETE CASCADE,
    release_id  BIGINT REFERENCES public.plugin_releases(id) ON DELETE SET NULL,
    tenant_id   TEXT,                 -- nullable for unauthenticated preview
    user_id     TEXT,
    ip_hash     TEXT,                 -- sha256(ip + salt), GDPR-friendly
    user_agent  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_plugin_downloads_plugin
    ON public.plugin_downloads(plugin_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_plugin_downloads_release
    ON public.plugin_downloads(release_id);

CREATE INDEX IF NOT EXISTS idx_plugin_downloads_tenant
    ON public.plugin_downloads(tenant_id);

COMMENT ON TABLE public.plugin_downloads IS
    'Per-install telemetry. ip_hash is one-way salted (see service code).';

-- ---------------------------------------------------------------------------
-- plugin_purchases — billing ledger for paid plugins
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.plugin_purchases (
    id              BIGSERIAL PRIMARY KEY,
    plugin_id       BIGINT NOT NULL REFERENCES public.marketplace_plugins(id) ON DELETE CASCADE,
    release_id      BIGINT REFERENCES public.plugin_releases(id) ON DELETE SET NULL,
    tenant_id       TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    amount_cents    INTEGER NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'USD',
    payment_method  TEXT NOT NULL DEFAULT 'stripe'
                      CHECK (payment_method IN ('stripe', 'wechat', 'alipay', 'manual')),
    payment_status  TEXT NOT NULL DEFAULT 'pending'
                      CHECK (payment_status IN ('pending', 'paid', 'refunded', 'failed', 'cancelled')),
    payment_ref     TEXT,           -- external id (pi_xxx, wechat txn id, ...)
    author_share_cents INTEGER NOT NULL DEFAULT 0,  -- revenue share snapshot
    platform_share_cents INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    paid_at         TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_plugin_purchases_plugin
    ON public.plugin_purchases(plugin_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_plugin_purchases_tenant
    ON public.plugin_purchases(tenant_id);

CREATE INDEX IF NOT EXISTS idx_plugin_purchases_status
    ON public.plugin_purchases(payment_status);

COMMENT ON TABLE public.plugin_purchases IS
    'Billing ledger for paid plugins. amount_cents and the two shares are '
    'snapshotted at purchase time so changes to revenue_share never retro.';

-- ---------------------------------------------------------------------------
-- marketplace_audit — append-only admin log (publish / review / install)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.marketplace_audit (
    id          BIGSERIAL PRIMARY KEY,
    plugin_id   BIGINT REFERENCES public.marketplace_plugins(id) ON DELETE CASCADE,
    release_id  BIGINT REFERENCES public.plugin_releases(id) ON DELETE CASCADE,
    action      TEXT NOT NULL
                  CHECK (action IN (
                      'publish', 'update', 'approve', 'reject',
                      'install', 'uninstall', 'review', 'purchase',
                      'webhook_received', 'deprecated'
                  )),
    actor       TEXT,                -- user_id / 'system' / 'webhook:<src>'
    detail      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_marketplace_audit_plugin
    ON public.marketplace_audit(plugin_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_marketplace_audit_action
    ON public.marketplace_audit(action, created_at DESC);

COMMENT ON TABLE public.marketplace_audit IS
    'Append-only audit trail. SOC2-relevant. Powers the admin review UI.';

-- ---------------------------------------------------------------------------
-- RLS — public read of approved plugins, service-role write
-- ---------------------------------------------------------------------------
ALTER TABLE public.marketplace_plugins ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.plugin_releases    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.plugin_reviews     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.plugin_downloads   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.plugin_purchases   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.marketplace_audit  ENABLE ROW LEVEL SECURITY;

-- Public: read approved listings
DROP POLICY IF EXISTS marketplace_plugins_public_read ON public.marketplace_plugins;
CREATE POLICY marketplace_plugins_public_read ON public.marketplace_plugins
  FOR SELECT TO anon, authenticated
  USING (status = 'approved');

-- Public: read approved releases of approved plugins
DROP POLICY IF EXISTS plugin_releases_public_read ON public.plugin_releases;
CREATE POLICY plugin_releases_public_read ON public.plugin_releases
  FOR SELECT TO anon, authenticated
  USING (
      status = 'approved'
      AND EXISTS (
          SELECT 1 FROM public.marketplace_plugins p
          WHERE p.id = plugin_releases.plugin_id AND p.status = 'approved'
      )
  );

-- Public: read published reviews of approved plugins
DROP POLICY IF EXISTS plugin_reviews_public_read ON public.plugin_reviews;
CREATE POLICY plugin_reviews_public_read ON public.plugin_reviews
  FOR SELECT TO anon, authenticated
  USING (
      status = 'published'
      AND EXISTS (
          SELECT 1 FROM public.marketplace_plugins p
          WHERE p.id = plugin_reviews.plugin_id AND p.status = 'approved'
      )
  );

-- Authenticated user can publish a review
DROP POLICY IF EXISTS plugin_reviews_insert ON public.plugin_reviews;
CREATE POLICY plugin_reviews_insert ON public.plugin_reviews
  FOR INSERT TO authenticated
  WITH CHECK (true);

-- Authenticated can record a download (best-effort)
DROP POLICY IF EXISTS plugin_downloads_insert ON public.plugin_downloads;
CREATE POLICY plugin_downloads_insert ON public.plugin_downloads
  FOR INSERT TO authenticated
  WITH CHECK (true);

-- Tenant-scoped read of own purchases
DROP POLICY IF EXISTS plugin_purchases_tenant ON public.plugin_purchases;
CREATE POLICY plugin_purchases_tenant ON public.plugin_purchases
  FOR SELECT TO authenticated
  USING (tenant_id = current_setting('app.tenant_id', true));

-- Service-role bypass
DROP POLICY IF EXISTS marketplace_plugins_service ON public.marketplace_plugins;
CREATE POLICY marketplace_plugins_service ON public.marketplace_plugins
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS plugin_releases_service ON public.plugin_releases;
CREATE POLICY plugin_releases_service ON public.plugin_releases
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS plugin_reviews_service ON public.plugin_reviews;
CREATE POLICY plugin_reviews_service ON public.plugin_reviews
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS plugin_downloads_service ON public.plugin_downloads;
CREATE POLICY plugin_downloads_service ON public.plugin_downloads
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS plugin_purchases_service ON public.plugin_purchases;
CREATE POLICY plugin_purchases_service ON public.plugin_purchases
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS marketplace_audit_service ON public.marketplace_audit;
CREATE POLICY marketplace_audit_service ON public.marketplace_audit
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ---------------------------------------------------------------------------
-- updated_at triggers
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.tg_set_updated_at_marketplace()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_marketplace_plugins_updated ON public.marketplace_plugins;
CREATE TRIGGER trg_marketplace_plugins_updated
  BEFORE UPDATE ON public.marketplace_plugins
  FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at_marketplace();

DROP TRIGGER IF EXISTS trg_plugin_reviews_updated ON public.plugin_reviews;
CREATE TRIGGER trg_plugin_reviews_updated
  BEFORE UPDATE ON public.plugin_reviews
  FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at_marketplace();

COMMIT;
