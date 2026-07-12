-- ============================================================================
-- 044_referrals.sql
-- 内部推荐系统 (T2405)
--
-- 1. ``referrals`` — 推荐记录 (推荐人→候选人→岗位)
-- 2. ``referral_points`` — 积分明细 (推荐人获得)
-- 3. ``referral_bonuses`` — 现金奖励 (入职后发放)
-- ============================================================================


-- ---------------------------------------------------------------------------
-- 1. referrals
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS referrals (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_id     uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    candidate_email text        NOT NULL,
    candidate_name  text,
    candidate_phone text,
    candidate_id    uuid        REFERENCES users(id) ON DELETE SET NULL,  -- 入职后绑定
    role_id         uuid        REFERENCES roles(id) ON DELETE SET NULL,
    job_title       text,

    -- 状态: pending → reviewed → interview → offered → hired → reward
    status          text        NOT NULL DEFAULT 'pending'
                                CHECK (status IN (
                                    'pending', 'reviewed', 'interview',
                                    'offered', 'hired', 'rewarded', 'rejected'
                                )),

    -- 备注
    notes           text,
    hr_notes        text,

    -- 奖励
    points_awarded  integer     DEFAULT 0,
    bonus_amount    NUMERIC(10, 2) DEFAULT 0,
    bonus_currency  text        DEFAULT 'CNY',

    -- 时间线
    reviewed_at     timestamptz,
    interview_at    timestamptz,
    offered_at      timestamptz,
    hired_at        timestamptz,
    reward_at       timestamptz,

    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    -- 防作弊: 同一候选人邮箱 + 同一岗位 只能被推荐一次 (UNIQUE)
    CONSTRAINT uq_referral UNIQUE (referrer_id, candidate_email, role_id)
);

CREATE INDEX IF NOT EXISTS idx_referrals_referrer
    ON referrals (referrer_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_referrals_status
    ON referrals (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_referrals_email
    ON referrals (candidate_email);

CREATE INDEX IF NOT EXISTS idx_referrals_role
    ON referrals (role_id, status);

COMMENT ON TABLE referrals IS '内部推荐记录 (T2405)';


-- ---------------------------------------------------------------------------
-- 2. referral_points
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS referral_points (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_id     uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    referral_id     uuid        REFERENCES referrals(id) ON DELETE SET NULL,
    -- 积分变化 (+/-)
    points          integer     NOT NULL,
    -- 原因: submission (+5) / interview (+20) / hired (+100) / redemption (-50)
    reason          text        NOT NULL,
    description     text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_referral_points_referrer
    ON referral_points (referrer_id, created_at DESC);

COMMENT ON TABLE referral_points IS '推荐积分明细';


-- ---------------------------------------------------------------------------
-- 3. referral_bonuses
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS referral_bonuses (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_id     uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    referral_id     uuid        NOT NULL REFERENCES referrals(id) ON DELETE CASCADE,
    amount          NUMERIC(10, 2) NOT NULL,
    currency        text        NOT NULL DEFAULT 'CNY',
    status          text        NOT NULL DEFAULT 'pending'  -- pending / paid / cancelled
                                CHECK (status IN ('pending', 'paid', 'cancelled')),
    payment_ref     text,
    paid_at         timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_referral_bonuses_referrer
    ON referral_bonuses (referrer_id, created_at DESC);

COMMENT ON TABLE referral_bonuses IS '推荐现金奖励 (默认 5000 CNY)';


-- ---------------------------------------------------------------------------
-- 默认奖励常量
-- ---------------------------------------------------------------------------

COMMENT ON COLUMN referrals.bonus_amount IS '入职后现金奖励, 默认 5000 CNY';


-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------

ALTER TABLE referrals ENABLE ROW LEVEL SECURITY;
ALTER TABLE referral_points ENABLE ROW LEVEL SECURITY;
ALTER TABLE referral_bonuses ENABLE ROW LEVEL SECURITY;

-- 推荐人可读自己的推荐
CREATE POLICY IF NOT EXISTS "推荐人可读自己的推荐"
    ON referrals FOR SELECT
    USING (referrer_id = auth.uid());

-- HR 全权
CREATE POLICY IF NOT EXISTS "HR可访问所有推荐"
    ON referrals FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM users u
            WHERE u.id = auth.uid()
            AND u.role IN ('hr', 'admin', 'manager')
        )
    );

-- 积分本人可读
CREATE POLICY IF NOT EXISTS "本人可读积分"
    ON referral_points FOR SELECT
    USING (referrer_id = auth.uid());

-- 奖励本人可读
CREATE POLICY IF NOT EXISTS "本人可读奖励"
    ON referral_bonuses FOR SELECT
    USING (referrer_id = auth.uid());
