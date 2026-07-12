-- ============================================================
-- Migration 024: Recruitment Funnel + Channel Attribution (T1303)
-- ============================================================

-- ------------------------------------------------------------
-- 漏斗事件 — 每个候选人-角色管道阶段事件
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS funnel_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID,
    candidate_id    UUID NOT NULL,
    role_id         UUID,
    stage           VARCHAR(32) NOT NULL,
        -- sourced / applied / screened / interviewed / offered / hired
    source          VARCHAR(64) NOT NULL DEFAULT 'unknown',
        -- linkedin / referral / indeed / company_site / direct / etc.
    cost_cents      INTEGER NOT NULL DEFAULT 0,
    metadata        JSONB NOT NULL DEFAULT '{}'::JSONB,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_funnel_events_org_time
    ON funnel_events(org_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_funnel_events_stage
    ON funnel_events(stage);
CREATE INDEX IF NOT EXISTS idx_funnel_events_source
    ON funnel_events(source);
CREATE INDEX IF NOT EXISTS idx_funnel_events_candidate
    ON funnel_events(candidate_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_funnel_events_role
    ON funnel_events(role_id, occurred_at DESC);

-- ------------------------------------------------------------
-- 渠道 ROI 配置 — 每个渠道的成本与花费记录(可选,用于 ROI 计算)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS channel_spend (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    channel         VARCHAR(64) NOT NULL,
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    spend_cents     INTEGER NOT NULL DEFAULT 0,
    notes           TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_channel_spend_org
    ON channel_spend(org_id, period_start DESC);
CREATE INDEX IF NOT EXISTS idx_channel_spend_channel
    ON channel_spend(channel);

-- ------------------------------------------------------------
-- RLS — talent_partner / admin 可读;admin 可写
-- ------------------------------------------------------------
ALTER TABLE funnel_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE channel_spend ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS funnel_events_read ON funnel_events;
CREATE POLICY funnel_events_read ON funnel_events
    FOR SELECT USING (
        auth.uid() IS NOT NULL
        AND (
            org_id IS NULL
            OR org_id::text = coalesce(
                (auth.jwt() ->> 'user_metadata')::jsonb ->> 'org_id',
                ''
            )
        )
    );

DROP POLICY IF EXISTS funnel_events_write ON funnel_events;
CREATE POLICY funnel_events_write ON funnel_events
    FOR INSERT WITH CHECK (
        auth.uid() IS NOT NULL
        AND (
            (auth.jwt() ->> 'user_metadata')::jsonb ->> 'role' = 'admin'
            OR (auth.jwt() ->> 'user_metadata')::jsonb ->> 'role' = 'talent_partner'
        )
    );

DROP POLICY IF EXISTS channel_spend_admin_read ON channel_spend;
CREATE POLICY channel_spend_admin_read ON channel_spend
    FOR SELECT USING (
        (auth.jwt() ->> 'user_metadata')::jsonb ->> 'role' = 'admin'
        OR (auth.jwt() ->> 'user_metadata')::jsonb ->> 'role' = 'talent_partner'
    );

DROP POLICY IF EXISTS channel_spend_admin_write ON channel_spend;
CREATE POLICY channel_spend_admin_write ON channel_spend
    FOR ALL USING (
        (auth.jwt() ->> 'user_metadata')::jsonb ->> 'role' = 'admin'
    );