-- ============================================================
-- Migration 022: AI 自动面试 (T1301)
-- 表:
--   ai_interviews         一次面试会话
--   ai_interview_questions  一会话下所有题目(可能是混合题)
--   ai_interview_answers    候选人每题的回答 + 转写 + AI 评分
--   ai_interview_reports    最终报告(逐题聚合 + 维度)
-- ============================================================

-- ------------------------------------------------------------
-- AI 面试会话
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_interviews (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,                       -- 候选人
    role                VARCHAR(64) NOT NULL,                -- 岗位 category
    role_label          VARCHAR(255),                        -- 显示名称
    difficulty          VARCHAR(16) NOT NULL DEFAULT 'mid',
    total_questions     INT NOT NULL DEFAULT 10,
    status              VARCHAR(16) NOT NULL DEFAULT 'created',
    -- created / in_progress / completed / abandoned / failed
    language            VARCHAR(16) NOT NULL DEFAULT 'auto',
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    extra               JSONB NOT NULL DEFAULT '{}'::JSONB, -- 题库 + LLM 配置等
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_interviews_user ON ai_interviews(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_interviews_status ON ai_interviews(status);

-- ------------------------------------------------------------
-- 题目(snapshot): 同一会话的题可能混合静态 + LLM 生成
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_interview_questions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id        UUID NOT NULL REFERENCES ai_interviews(id) ON DELETE CASCADE,
    seq                 INT NOT NULL,                       -- 第几题(从 1 开始)
    category            VARCHAR(64) NOT NULL,
    title               VARCHAR(255) NOT NULL,
    prompt              TEXT NOT NULL,
    expected_points     JSONB NOT NULL DEFAULT '[]'::JSONB,
    skills              JSONB NOT NULL DEFAULT '[]'::JSONB,
    difficulty          VARCHAR(16) NOT NULL DEFAULT 'mid',
    qtype               VARCHAR(32) NOT NULL DEFAULT 'behavioral',
    duration_sec        INT NOT NULL DEFAULT 120,
    weights             JSONB NOT NULL DEFAULT '{}'::JSONB,
    source              VARCHAR(16) NOT NULL DEFAULT 'static', -- static / llm
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (interview_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_ai_interview_q_session ON ai_interview_questions(interview_id, seq);

-- ------------------------------------------------------------
-- 回答(含转写 + 视频链接 + 评分)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_interview_answers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id        UUID NOT NULL REFERENCES ai_interviews(id) ON DELETE CASCADE,
    question_id         UUID NOT NULL REFERENCES ai_interview_questions(id) ON DELETE CASCADE,
    seq                 INT NOT NULL,
    video_url           TEXT,
    audio_object_key    TEXT,
    transcript          TEXT NOT NULL DEFAULT '',
    transcript_provider VARCHAR(32) NOT NULL DEFAULT 'mock_stt',
    duration_sec        DOUBLE PRECISION,
    overall             DOUBLE PRECISION,                   -- 0-100
    band                VARCHAR(16),                        -- weak/fair/good/excellent
    dimensions          JSONB NOT NULL DEFAULT '{}'::JSONB, -- {communication: 78, ...}
    strengths           JSONB NOT NULL DEFAULT '[]'::JSONB,
    improvements        JSONB NOT NULL DEFAULT '[]'::JSONB,
    feedback            TEXT,
    vision_notes        TEXT,
    raw                 JSONB NOT NULL DEFAULT '{}'::JSONB,
    submitted_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (interview_id, question_id)
);

CREATE INDEX IF NOT EXISTS idx_ai_interview_answers_session ON ai_interview_answers(interview_id);
CREATE INDEX IF NOT EXISTS idx_ai_interview_answers_band ON ai_interview_answers(band);

-- ------------------------------------------------------------
-- 最终报告(冗余存储,加快仪表盘读取)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_interview_reports (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id        UUID NOT NULL UNIQUE REFERENCES ai_interviews(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL,
    role                VARCHAR(64) NOT NULL,
    overall_score       DOUBLE PRECISION NOT NULL DEFAULT 0,
    dimension_scores    JSONB NOT NULL DEFAULT '{}'::JSONB,
    radar               JSONB NOT NULL DEFAULT '{}'::JSONB,
    summary             TEXT NOT NULL DEFAULT '',
    recommendation      VARCHAR(16) NOT NULL DEFAULT 'consider',
    -- strong_yes / yes / consider / no
    strengths           JSONB NOT NULL DEFAULT '[]'::JSONB,
    improvements        JSONB NOT NULL DEFAULT '[]'::JSONB,
    total_questions     INT NOT NULL DEFAULT 0,
    answered_questions  INT NOT NULL DEFAULT 0,
    provider            VARCHAR(32) NOT NULL DEFAULT 'mock',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_interview_reports_user ON ai_interview_reports(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_interview_reports_overall ON ai_interview_reports(overall_score DESC);

-- ------------------------------------------------------------
-- Row Level Security (jobseeker own data only)
-- ------------------------------------------------------------
ALTER TABLE ai_interviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_interview_questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_interview_answers ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_interview_reports ENABLE ROW LEVEL SECURITY;

-- Candidates can read their own interviews
DROP POLICY IF EXISTS ai_interviews_self_select ON ai_interviews;
CREATE POLICY ai_interviews_self_select ON ai_interviews
    FOR SELECT USING (user_id = auth.uid());

DROP POLICY IF EXISTS ai_interviews_self_modify ON ai_interviews;
CREATE POLICY ai_interviews_self_modify ON ai_interviews
    FOR ALL USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS ai_interview_q_select ON ai_interview_questions;
CREATE POLICY ai_interview_q_select ON ai_interview_questions
    FOR SELECT USING (
        EXISTS (SELECT 1 FROM ai_interviews i WHERE i.id = interview_id AND i.user_id = auth.uid())
    );

DROP POLICY IF EXISTS ai_interview_q_modify ON ai_interview_questions;
CREATE POLICY ai_interview_q_modify ON ai_interview_questions
    FOR ALL USING (
        EXISTS (SELECT 1 FROM ai_interviews i WHERE i.id = interview_id AND i.user_id = auth.uid())
    )
    WITH CHECK (
        EXISTS (SELECT 1 FROM ai_interviews i WHERE i.id = interview_id AND i.user_id = auth.uid())
    );

DROP POLICY IF EXISTS ai_interview_a_select ON ai_interview_answers;
CREATE POLICY ai_interview_a_select ON ai_interview_answers
    FOR SELECT USING (
        EXISTS (SELECT 1 FROM ai_interviews i WHERE i.id = interview_id AND i.user_id = auth.uid())
    );

DROP POLICY IF EXISTS ai_interview_a_modify ON ai_interview_answers;
CREATE POLICY ai_interview_a_modify ON ai_interview_answers
    FOR ALL USING (
        EXISTS (SELECT 1 FROM ai_interviews i WHERE i.id = interview_id AND i.user_id = auth.uid())
    )
    WITH CHECK (
        EXISTS (SELECT 1 FROM ai_interviews i WHERE i.id = interview_id AND i.user_id = auth.uid())
    );

DROP POLICY IF EXISTS ai_interview_r_select ON ai_interview_reports;
CREATE POLICY ai_interview_r_select ON ai_interview_reports
    FOR SELECT USING (user_id = auth.uid());

DROP POLICY IF EXISTS ai_interview_r_modify ON ai_interview_reports;
CREATE POLICY ai_interview_r_modify ON ai_interview_reports
    FOR ALL USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- updated_at trigger
DROP TRIGGER IF EXISTS trg_ai_interviews_updated_at ON ai_interviews;
CREATE TRIGGER trg_ai_interviews_updated_at
    BEFORE UPDATE ON ai_interviews
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
