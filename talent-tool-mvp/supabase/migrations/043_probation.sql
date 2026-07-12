-- ============================================================================
-- 043_probation.sql
-- 试用期跟踪 (T2404)
--
-- 1. ``probation_reviews`` — 试用期评估记录 (5 维度评分)
-- 2. ``probation_tasks`` — 自动任务: 入职当天 / D+30 / D+90 / D+180
-- 3. ``probation_extensions`` — 延期记录
-- ============================================================================


-- ---------------------------------------------------------------------------
-- 1. probation_reviews (评估记录)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS probation_reviews (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id         uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    manager_id          uuid        REFERENCES users(id) ON DELETE SET NULL,
    org_id              text        NOT NULL,

    -- 评估阶段: 30 / 90 / 180 / completion
    review_stage        text        NOT NULL CHECK (review_stage IN ('30', '90', '180', 'completion', 'final')),
    -- 评估日期
    review_date         date        NOT NULL,

    -- 5 维度评分 (1-5): 绩效/学习/融入/态度/潜力
    scores              jsonb       NOT NULL DEFAULT '{}'::jsonb,

    -- 评语
    comments            text,

    -- 状态: pending / submitted / passed / failed / extended
    status              text        NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending', 'submitted', 'passed', 'failed', 'extended')),

    -- 转正日期 (转正时填)
    confirmed_at        timestamptz,
    confirmation_notes  text,

    -- 延期天数 (如适用)
    extension_days      integer     DEFAULT 0,

    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_extension_days CHECK (extension_days >= 0 AND extension_days <= 90)
);

CREATE INDEX IF NOT EXISTS idx_probation_reviews_employee
    ON probation_reviews (employee_id, review_date DESC);

CREATE INDEX IF NOT EXISTS idx_probation_reviews_org
    ON probation_reviews (org_id, status);

CREATE INDEX IF NOT EXISTS idx_probation_reviews_manager
    ON probation_reviews (manager_id, status, review_date);

COMMENT ON TABLE probation_reviews IS '试用期评估记录 (5 维度评分, T2404)';
COMMENT ON COLUMN probation_reviews.scores IS '{performance: 4, learning: 5, integration: 3, attitude: 5, potential: 4}';


-- ---------------------------------------------------------------------------
-- 2. probation_tasks (自动任务)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS probation_tasks (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id     uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id          text        NOT NULL,

    -- 任务类型: orientation / checkin_30 / review_30 / review_90 / review_180
    type            text        NOT NULL CHECK (type IN (
        'orientation', 'checkin_30', 'review_30', 'review_90', 'review_180', 'reminder'
    )),
    title           text        NOT NULL,
    description     text,

    -- 截止时间
    due_at          timestamptz NOT NULL,
    -- 完成时间
    completed_at    timestamptz,

    -- 关联 review (如适用)
    review_id       uuid        REFERENCES probation_reviews(id) ON DELETE SET NULL,

    -- 提醒发送时间
    reminded_at     timestamptz,

    created_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_probation_tasks UNIQUE (employee_id, type, due_at)
);

CREATE INDEX IF NOT EXISTS idx_probation_tasks_employee
    ON probation_tasks (employee_id, due_at);

CREATE INDEX IF NOT EXISTS idx_probation_tasks_pending
    ON probation_tasks (due_at)
    WHERE completed_at IS NULL;

COMMENT ON TABLE probation_tasks IS '试用期自动任务 (入职/D+30/D+90/D+180)';


-- ---------------------------------------------------------------------------
-- 3. probation_extensions (延期)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS probation_extensions (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id     uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    original_end    date        NOT NULL,
    extended_end    date        NOT NULL,
    reason          text,
    approved_by     uuid        REFERENCES users(id) ON DELETE SET NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_probation_extensions_employee
    ON probation_extensions (employee_id, created_at DESC);

COMMENT ON TABLE probation_extensions IS '试用期延期记录';


-- ---------------------------------------------------------------------------
-- RLS Policies
-- ---------------------------------------------------------------------------

ALTER TABLE probation_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE probation_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE probation_extensions ENABLE ROW LEVEL SECURITY;

-- 员工可以查看自己的评估
CREATE POLICY IF NOT EXISTS "员工可读自己的评估"
    ON probation_reviews FOR SELECT
    USING (employee_id = auth.uid());

-- 经理可以查看/修改团队的评估
CREATE POLICY IF NOT EXISTS "经理可访问团队评估"
    ON probation_reviews FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM users u
            WHERE u.id = auth.uid()
            AND u.org_id = probation_reviews.org_id
            AND u.role IN ('hr', 'manager', 'admin')
        )
    );

-- 员工可读自己的任务
CREATE POLICY IF NOT EXISTS "员工可读自己的任务"
    ON probation_tasks FOR SELECT
    USING (employee_id = auth.uid());

-- HR/经理可读团队任务
CREATE POLICY IF NOT EXISTS "HR可读团队任务"
    ON probation_tasks FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM users u
            WHERE u.id = auth.uid()
            AND u.org_id = probation_tasks.org_id
            AND u.role IN ('hr', 'manager', 'admin')
        )
    );

-- HR 可读延期
CREATE POLICY IF NOT EXISTS "HR可读延期"
    ON probation_extensions FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM users u
            WHERE u.id = auth.uid()
            AND u.role IN ('hr', 'manager', 'admin')
        )
    );
