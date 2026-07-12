-- ============================================================
-- Migration 025: Job Subscriptions (T1304)
-- ============================================================

CREATE TABLE IF NOT EXISTS job_subscriptions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    name            VARCHAR(255) NOT NULL DEFAULT '',
    criteria        JSONB NOT NULL DEFAULT '{}'::JSONB,
        -- { role, city, salary_min, currency, skills[], seniority, remote_policy }
    channels        JSONB NOT NULL DEFAULT '["web"]'::JSONB,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    last_matched_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_subscriptions_user
    ON job_subscriptions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_subscriptions_enabled
    ON job_subscriptions(enabled) WHERE enabled = TRUE;

-- ------------------------------------------------------------
-- 触发器: updated_at 自动更新
-- ------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_job_subscriptions_updated_at ON job_subscriptions;
CREATE TRIGGER trg_job_subscriptions_updated_at
    BEFORE UPDATE ON job_subscriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ------------------------------------------------------------
-- RLS: 候选人本人读写
-- ------------------------------------------------------------
ALTER TABLE job_subscriptions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS job_subscriptions_self ON job_subscriptions;
CREATE POLICY job_subscriptions_self ON job_subscriptions
    FOR ALL USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());