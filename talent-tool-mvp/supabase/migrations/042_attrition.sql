-- ============================================================================
-- 042_attrition.sql
-- 离职风险预测 (T2403)
--
-- 1. ``attrition_risks`` — 单用户风险快照 (按 computed_at 倒序, 保留 30 天历史)
-- 2. ``attrition_feedback`` — HR 反馈 (实际是否离职), 用于再训练
--
-- 设计要点:
-- - risk_score: 0-1, NUMERIC 保证精度
-- - factors: jsonb 存储 top-3 风险因素 + 贡献度
-- - computed_at: timestamptz (含时区, 便于跨区域聚合)
-- - RLS: 用户可读自己; HR/manager 可读团队; admin 全权.
-- ============================================================================


-- ---------------------------------------------------------------------------
-- 1. attrition_risks (风险快照)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS attrition_risks (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- 风险分数 0-1
    risk_score      NUMERIC(4, 3) NOT NULL CHECK (risk_score BETWEEN 0 AND 1),
    -- 等级: low / medium / high
    risk_level      text        NOT NULL CHECK (risk_level IN ('low', 'medium', 'high')),

    -- 特征快照
    emotion_avg_30d     NUMERIC(5, 2),
    journal_freq_30d    integer,
    interaction_gap_h   NUMERIC(6, 2),
    negative_tickets    integer,
    task_completion     NUMERIC(4, 3),

    -- 关键因素 (top-3, jsonb)
    factors         jsonb       NOT NULL DEFAULT '[]'::jsonb,

    -- 自然语言解释
    explanation     text,

    -- 模型来源: lightgbm / llm / rules
    model_used      text        NOT NULL DEFAULT 'rules',

    computed_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_attrition_risks_user_time UNIQUE (user_id, computed_at)
);

CREATE INDEX IF NOT EXISTS idx_attrition_risks_user_time
    ON attrition_risks (user_id, computed_at DESC);

CREATE INDEX IF NOT EXISTS idx_attrition_risks_level
    ON attrition_risks (risk_level, computed_at DESC);

CREATE INDEX IF NOT EXISTS idx_attrition_risks_org
    ON attrition_risks (user_id, computed_at DESC)
    WHERE risk_level = 'high';

COMMENT ON TABLE attrition_risks IS
    'T2403 离职风险预测快照 — 用户按 computed_at 倒序取最新一条';
COMMENT ON COLUMN attrition_risks.risk_score IS
    '0-1 风险分数 (NUMERIC 保留精度)';
COMMENT ON COLUMN attrition_risks.factors IS
    'jsonb 数组, 元素 {key, contribution, description}';


-- ---------------------------------------------------------------------------
-- 2. attrition_feedback (HR 反馈, 用于再训练)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS attrition_feedback (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- HR 反馈: 是否真的离职了 (用于验证模型预测)
    actual_attrition    boolean NOT NULL,
    -- 离职日期 (若 actual_attrition=true)
    left_at             date,

    -- 预测时的 risk_score (用于分析偏差)
    predicted_score     NUMERIC(4, 3),

    -- 备注
    notes           text,

    -- 谁反馈
    recorded_by     uuid        REFERENCES users(id),
    recorded_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_attrition_feedback_user
    ON attrition_feedback (user_id, recorded_at DESC);

COMMENT ON TABLE attrition_feedback IS
    'T2403 HR 反馈 — 用于模型再训练, 验证风险预测的准确性';


-- ---------------------------------------------------------------------------
-- 3. RLS
-- ---------------------------------------------------------------------------

ALTER TABLE attrition_risks ENABLE ROW LEVEL SECURITY;
ALTER TABLE attrition_feedback ENABLE ROW LEVEL SECURITY;

-- 用户可读自己的最新风险
DROP POLICY IF EXISTS attr_read_self ON attrition_risks;
CREATE POLICY attr_read_self ON attrition_risks
    FOR SELECT
    USING (auth.uid() = user_id);

-- HR / manager / admin 可读所有
DROP POLICY IF EXISTS attr_read_all ON attrition_risks;
CREATE POLICY attr_read_all ON attrition_risks
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM users u
            WHERE u.id = auth.uid()
            AND u.role IN ('hr', 'manager', 'admin')
        )
    );

-- 仅 system / admin 可写
DROP POLICY IF EXISTS attr_write_admin ON attrition_risks;
CREATE POLICY attr_write_admin ON attrition_risks
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM users u
            WHERE u.id = auth.uid()
            AND u.role = 'admin'
        )
    );

-- feedback: HR/admin 可写
DROP POLICY IF EXISTS attr_feedback_write ON attrition_feedback;
CREATE POLICY attr_feedback_write ON attrition_feedback
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM users u
            WHERE u.id = auth.uid()
            AND u.role IN ('hr', 'admin')
        )
    );

DROP POLICY IF EXISTS attr_feedback_read ON attrition_feedback;
CREATE POLICY attr_feedback_read ON attrition_feedback
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM users u
            WHERE u.id = auth.uid()
            AND u.role IN ('hr', 'admin')
        )
    );