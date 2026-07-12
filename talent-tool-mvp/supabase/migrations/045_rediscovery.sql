-- ============================================================================
-- 045_rediscovery.sql
-- 候选人激活/沉睡库 (T2406)
--
-- 1. ``rediscovery_log`` — 激活事件日志 (HR 主动触达)
-- 2. ``rediscovery_profiles`` — 候选人画像 (LLM 评估)
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. rediscovery_log
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS rediscovery_log (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id    uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- 上次活跃时间
    last_active_at  timestamptz,
    -- 触发激活时间
    activated_at    timestamptz NOT NULL DEFAULT now(),
    -- 是否转化 (再次进入流程)
    converted       boolean     NOT NULL DEFAULT false,
    converted_at    timestamptz,
    -- 触达通道: im / email / sms / dingtalk
    channel         text        NOT NULL CHECK (channel IN ('im', 'email', 'sms', 'dingtalk')),
    -- 策略: conservative / standard / aggressive
    strategy        text        NOT NULL CHECK (strategy IN ('conservative', 'standard', 'aggressive')),

    -- LLM 评估 (jsonb): reason / score / matched_role_ids
    llm_eval        jsonb,
    -- 消息内容
    message         text,

    -- 发起人 (HR)
    triggered_by    uuid        REFERENCES users(id) ON DELETE SET NULL,

    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rediscovery_log_candidate
    ON rediscovery_log (candidate_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rediscovery_log_conversion
    ON rediscovery_log (converted, strategy, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rediscovery_log_recent
    ON rediscovery_log (created_at DESC);

COMMENT ON TABLE rediscovery_log IS '候选人激活日志 (T2406)';


-- ---------------------------------------------------------------------------
-- 2. rediscovery_profiles
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS rediscovery_profiles (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id    uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- 基础属性
    last_active_at  timestamptz,
    dormant_days    integer     NOT NULL,
    -- 画像标签
    job_titles      text[]      DEFAULT '{}',
    skills          text[]      DEFAULT '{}',
    city            text,
    seniority       text,
    salary_expect   NUMERIC(10, 2),

    -- LLM 评分 0-1
    activity_score      NUMERIC(4, 3) DEFAULT 0.0,
    fit_score           NUMERIC(4, 3) DEFAULT 0.0,  -- 与新职位匹配度
    rediscover_potential NUMERIC(4, 3) DEFAULT 0.0, -- 综合激活潜力

    -- LLM 推荐原因
    reason          text,
    recommended_roles jsonb     DEFAULT '[]'::jsonb,

    computed_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_rediscovery_profiles UNIQUE (candidate_id, computed_at)
);

CREATE INDEX IF NOT EXISTS idx_rediscovery_profiles_potential
    ON rediscovery_profiles (rediscover_potential DESC, computed_at DESC)
    WHERE rediscover_potential >= 0.6;

COMMENT ON TABLE rediscovery_profiles IS '沉睡候选人画像 + LLM 评估';


-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------

ALTER TABLE rediscovery_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE rediscovery_profiles ENABLE ROW LEVEL SECURITY;

-- HR 可读写
CREATE POLICY IF NOT EXISTS "HR可访问 rediscovery_log"
    ON rediscovery_log FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM users u
            WHERE u.id = auth.uid()
            AND u.role IN ('hr', 'admin', 'manager')
        )
    );

-- 候选人可读自己的
CREATE POLICY IF NOT EXISTS "候选人可读自己的画像"
    ON rediscovery_profiles FOR SELECT
    USING (candidate_id = auth.uid());

CREATE POLICY IF NOT EXISTS "HR可读画像"
    ON rediscovery_profiles FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM users u
            WHERE u.id = auth.uid()
            AND u.role IN ('hr', 'admin', 'manager')
        )
    );
