-- ============================================================
-- Migration 006: 澄清产物 (画像 + 真实需求)
-- ============================================================

-- 求职者画像与需求
CREATE TABLE IF NOT EXISTS candidate_clarifications (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,                -- 求职者 user_id
    candidate_id        UUID REFERENCES candidates(id) ON DELETE CASCADE,
    -- 清晰画像 (1.5.1)
    profile_synthesis   JSONB NOT NULL DEFAULT '{}'::jsonb,   -- 综合画像
    explicit_skills     JSONB DEFAULT '[]'::jsonb,
    implicit_traits     JSONB DEFAULT '[]'::jsonb,    -- 隐性特质
    value_orientation   JSONB DEFAULT '{}'::jsonb,    -- 价值观
    -- 真实需求 (1.5.2)
    explicit_needs      JSONB DEFAULT '[]'::jsonb,    -- 显性需求
    implicit_needs      JSONB DEFAULT '[]'::jsonb,    -- 隐性需求
    must_haves          JSONB DEFAULT '[]'::jsonb,
    nice_to_haves       JSONB DEFAULT '[]'::jsonb,
    deal_breakers       JSONB DEFAULT '[]'::jsonb,
    -- 元数据
    confidence_score    NUMERIC(3,2) DEFAULT 0.5,
    info_completeness   NUMERIC(3,2) DEFAULT 0.0,     -- 信息完整度 0~1
    conflict_flags      JSONB DEFAULT '[]'::jsonb,    -- 检测到的冲突
    follow_up_questions JSONB DEFAULT '[]'::jsonb,    -- 建议追问
    last_synthesized_at TIMESTAMPTZ DEFAULT NOW(),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_candidate_clarifications_user
    ON candidate_clarifications (user_id, last_synthesized_at DESC);

-- 用人方画像与需求 (人才画像 + 岗位真实需求)
CREATE TABLE IF NOT EXISTS employer_clarifications (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id     UUID NOT NULL,
    role_id             UUID REFERENCES roles(id) ON DELETE CASCADE,
    -- 所需人才清晰画像 (2.8.1)
    talent_image        JSONB NOT NULL DEFAULT '{}'::jsonb,
    hard_skills         JSONB DEFAULT '[]'::jsonb,
    soft_skills         JSONB DEFAULT '[]'::jsonb,
    experience_profile  JSONB DEFAULT '{}'::jsonb,
    cultural_fit        JSONB DEFAULT '{}'::jsonb,
    -- 岗位真实需求 (2.8.2)
    explicit_requirements JSONB DEFAULT '[]'::jsonb,
    implicit_requirements JSONB DEFAULT '[]'::jsonb,
    must_haves          JSONB DEFAULT '[]'::jsonb,
    nice_to_haves       JSONB DEFAULT '[]'::jsonb,
    -- 多方意见汇总
    contributor_inputs  JSONB DEFAULT '[]'::jsonb,    -- 各角色输入快照
    conflicts           JSONB DEFAULT '[]'::jsonb,    -- 角色间冲突
    consensus_score     NUMERIC(3,2) DEFAULT 0.5,
    -- 元数据
    confidence_score    NUMERIC(3,2) DEFAULT 0.5,
    follow_up_questions JSONB DEFAULT '[]'::jsonb,
    last_synthesized_at TIMESTAMPTZ DEFAULT NOW(),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_employer_clarifications_role
    ON employer_clarifications (role_id, last_synthesized_at DESC);

-- 启用 RLS
ALTER TABLE candidate_clarifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE employer_clarifications ENABLE ROW LEVEL SECURITY;

CREATE POLICY "User own clarification" ON candidate_clarifications
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Org members see employer clarification" ON employer_clarifications
    FOR ALL USING (true) WITH CHECK (true);

-- 日报 (T102)
CREATE TABLE IF NOT EXISTS daily_journals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    journal_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    content         TEXT NOT NULL,                    -- 当日工作内容/困惑/心得
    mood_score      NUMERIC(3,2),                     -- 当日情绪 -1~1
    topics          JSONB DEFAULT '[]'::jsonb,        -- 提取的关键词
    -- AI 评价
    ai_rating       TEXT,                             -- excellent/good/needs_improvement
    ai_advice       TEXT,                             -- 智能体给的建议
    ai_warnings     JSONB DEFAULT '[]'::jsonb,        -- 注意事项
    ai_action_items JSONB DEFAULT '[]'::jsonb,        -- AI 给的行动建议
    advisor_agent   TEXT,
    reviewed_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, journal_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_journals_user_date
    ON daily_journals (user_id, journal_date DESC);

ALTER TABLE daily_journals ENABLE ROW LEVEL SECURITY;
CREATE POLICY "User own journals" ON daily_journals
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- 职业规划 (T105)
CREATE TABLE IF NOT EXISTS career_plans (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    short_term      JSONB DEFAULT '[]'::jsonb,        -- 3个月内
    mid_term        JSONB DEFAULT '[]'::jsonb,        -- 1年内
    long_term       JSONB DEFAULT '[]'::jsonb,        -- 3年+
    learning_paths  JSONB DEFAULT '[]'::jsonb,
    recommended_roles JSONB DEFAULT '[]'::jsonb,
    market_insights JSONB DEFAULT '{}'::jsonb,        -- 行情/薪资/趋势
    skill_gaps      JSONB DEFAULT '[]'::jsonb,
    milestones      JSONB DEFAULT '[]'::jsonb,
    last_generated_at TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_career_plans_user ON career_plans (user_id, last_generated_at DESC);
ALTER TABLE career_plans ENABLE ROW LEVEL SECURITY;
CREATE POLICY "User own plan" ON career_plans FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- 双向匹配结果 (T301)
CREATE TABLE IF NOT EXISTS two_way_matches (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id        UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    role_id             UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    -- 双向分
    candidate_to_role   NUMERIC(4,3) NOT NULL,         -- 求职者对岗位的契合度
    role_to_candidate   NUMERIC(4,3) NOT NULL,         -- 岗位对求职者的契合度
    harmonic_score      NUMERIC(4,3) NOT NULL,         -- 调和值
    -- 详情
    candidate_perspective JSONB DEFAULT '{}'::jsonb,   -- 求职者视角的优劣
    employer_perspective  JSONB DEFAULT '{}'::jsonb,   -- 用人方视角的优劣
    mutual_score        NUMERIC(4,3),                  -- 互评分
    feedback_loop       JSONB DEFAULT '{}'::jsonb,     -- 反馈数据
    status              TEXT DEFAULT 'pending' CHECK (status IN (
        'pending', 'proposed', 'shortlisted', 'interviewing',
        'accepted', 'rejected_by_candidate', 'rejected_by_employer', 'placed'
    )),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (candidate_id, role_id)
);

CREATE INDEX IF NOT EXISTS idx_two_way_match_role ON two_way_matches (role_id, harmonic_score DESC);
CREATE INDEX IF NOT EXISTS idx_two_way_match_candidate ON two_way_matches (candidate_id, harmonic_score DESC);

ALTER TABLE two_way_matches ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public visible two-way match" ON two_way_matches FOR ALL USING (true) WITH CHECK (true);