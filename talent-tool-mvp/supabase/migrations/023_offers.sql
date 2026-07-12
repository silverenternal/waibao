-- ============================================================
-- Migration 023: Offers + Negotiation (T1302)
-- ============================================================

-- ------------------------------------------------------------
-- 用户保存的 Offer(候选人对自己收到的所有 offer)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_offers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    title               VARCHAR(255) NOT NULL DEFAULT '',
    company             VARCHAR(255) NOT NULL DEFAULT '',
    role_level          VARCHAR(64) NOT NULL DEFAULT '',
    location            VARCHAR(8) NOT NULL DEFAULT 'CN',    -- CN / US / SG
    currency            VARCHAR(8) NOT NULL DEFAULT 'CNY',
    base_salary         DOUBLE PRECISION NOT NULL DEFAULT 0,
    bonus               DOUBLE PRECISION NOT NULL DEFAULT 0,
    bonus_target_pct    DOUBLE PRECISION NOT NULL DEFAULT 0,
    equity_value        DOUBLE PRECISION NOT NULL DEFAULT 0,
    equity_vesting_years INT NOT NULL DEFAULT 4,
    benefits            DOUBLE PRECISION NOT NULL DEFAULT 0,
    signing_bonus       DOUBLE PRECISION NOT NULL DEFAULT 0,
    pto_days            INT NOT NULL DEFAULT 0,
    extras              JSONB NOT NULL DEFAULT '{}'::JSONB,
    deleted_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_offers_user ON user_offers(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_offers_alive ON user_offers(user_id) WHERE deleted_at IS NULL;

-- ------------------------------------------------------------
-- 谈判脚本历史
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS negotiation_scripts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    offer_id            UUID NOT NULL REFERENCES user_offers(id) ON DELETE CASCADE,
    region              VARCHAR(8) NOT NULL,
    currency            VARCHAR(8) NOT NULL,
    current_total       DOUBLE PRECISION NOT NULL DEFAULT 0,
    target_total        DOUBLE PRECISION NOT NULL DEFAULT 0,
    walkaway_threshold  DOUBLE PRECISION NOT NULL DEFAULT 0,
    percent_in_market   INT NOT NULL DEFAULT 50,
    market_band         JSONB NOT NULL DEFAULT '[]'::JSONB,
    talking_points      JSONB NOT NULL DEFAULT '[]'::JSONB,
    email_template      TEXT NOT NULL DEFAULT '',
    counter_examples    JSONB NOT NULL DEFAULT '[]'::JSONB,
    tactics             JSONB NOT NULL DEFAULT '[]'::JSONB,
    next_steps          JSONB NOT NULL DEFAULT '[]'::JSONB,
    provider            VARCHAR(32) NOT NULL DEFAULT 'mock',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_negotiation_scripts_user ON negotiation_scripts(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_negotiation_scripts_offer ON negotiation_scripts(offer_id);

-- ------------------------------------------------------------
-- 触发器
-- ------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_user_offers_updated_at ON user_offers;
CREATE TRIGGER trg_user_offers_updated_at
    BEFORE UPDATE ON user_offers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ------------------------------------------------------------
-- RLS (jobseeker 只能看自己的)
-- ------------------------------------------------------------
ALTER TABLE user_offers ENABLE ROW LEVEL SECURITY;
ALTER TABLE negotiation_scripts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_offers_self ON user_offers;
CREATE POLICY user_offers_self ON user_offers
    FOR ALL USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS negotiation_scripts_self ON negotiation_scripts;
CREATE POLICY negotiation_scripts_self ON negotiation_scripts
    FOR ALL USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());
