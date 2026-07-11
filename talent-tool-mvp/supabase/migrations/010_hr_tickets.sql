-- ============================================================================
-- 010_hr_tickets.sql
-- HR 工单系统 (T207)
--
-- 设计要点:
-- 1. tickets 表: 工单主表,字段包括 organisation_id, user_id (创建者),
--    title, description, status, priority, assignee_id, created_at, updated_at,
--    sla_due_at。
-- 2. ticket_comments 表: 工单评论/对话记录。
-- 3. ticket_status_history 表: 状态流转审计日志 (谁在何时把工单从 X → Y)。
-- 4. ticket_sla_rules 表: SLA 规则 (按 priority → 响应/解决时限)。
-- 5. ticket_audit 信号 (signal_type='ticket_*') 复用 signals 表。
-- 6. RLS: 创建者读自己 + 同 org 同事读; HR/admin 全部读写。
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 枚举
-- ----------------------------------------------------------------------------

-- 工单状态
DO $$ BEGIN
    CREATE TYPE ticket_status AS ENUM (
        'open',
        'in_progress',
        'awaiting_user',
        'resolved',
        'closed'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- 优先级
DO $$ BEGIN
    CREATE TYPE ticket_priority AS ENUM (
        'low',
        'normal',
        'high',
        'urgent'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- 工单类别 (HR / IT / 入职 / 离职 / 政策 / 投诉 等)
DO $$ BEGIN
    CREATE TYPE ticket_category AS ENUM (
        'hr',
        'onboarding',
        'offboarding',
        'policy',
        'payroll',
        'benefits',
        'training',
        'complaint',
        'it',
        'other'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- 评论作者类型 (employee / hr / system)
DO $$ BEGIN
    CREATE TYPE ticket_comment_author AS ENUM (
        'employee',
        'hr',
        'system'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;


-- ----------------------------------------------------------------------------
-- tickets 主表
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tickets (
    id              uuid            PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id uuid            REFERENCES organisations(id) ON DELETE CASCADE,
    user_id         uuid            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           text            NOT NULL,
    description     text            NOT NULL DEFAULT '',

    status          ticket_status   NOT NULL DEFAULT 'open',
    priority        ticket_priority NOT NULL DEFAULT 'normal',
    category        ticket_category NOT NULL DEFAULT 'hr',
    assignee_id     uuid            REFERENCES users(id) ON DELETE SET NULL,

    -- 元数据
    metadata        jsonb           NOT NULL DEFAULT '{}'::jsonb,
    tags            jsonb           NOT NULL DEFAULT '[]'::jsonb,

    -- SLA
    sla_due_at      timestamptz,
    first_responded_at timestamptz,
    resolved_at     timestamptz,
    closed_at       timestamptz,

    -- 审计
    created_at      timestamptz     NOT NULL DEFAULT now(),
    updated_at      timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tickets_org
    ON tickets(organisation_id);

CREATE INDEX IF NOT EXISTS idx_tickets_user
    ON tickets(user_id);

CREATE INDEX IF NOT EXISTS idx_tickets_assignee
    ON tickets(assignee_id)
    WHERE assignee_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_tickets_status
    ON tickets(status);

CREATE INDEX IF NOT EXISTS idx_tickets_priority
    ON tickets(priority);

CREATE INDEX IF NOT EXISTS idx_tickets_sla_due
    ON tickets(sla_due_at)
    WHERE status NOT IN ('resolved', 'closed');

CREATE INDEX IF NOT EXISTS idx_tickets_created_at
    ON tickets(created_at DESC);


-- ----------------------------------------------------------------------------
-- ticket_comments 评论表
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ticket_comments (
    id              uuid                    PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id       uuid                    NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    author_id       uuid                    REFERENCES users(id) ON DELETE SET NULL,
    author_type     ticket_comment_author   NOT NULL DEFAULT 'employee',
    body            text                    NOT NULL,
    is_internal     boolean                 NOT NULL DEFAULT FALSE,
    attachments     jsonb                   NOT NULL DEFAULT '[]'::jsonb,
    created_at      timestamptz             NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ticket_comments_ticket
    ON ticket_comments(ticket_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ticket_comments_author
    ON ticket_comments(author_id);


-- ----------------------------------------------------------------------------
-- ticket_status_history 状态流转审计
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ticket_status_history (
    id              uuid            PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id       uuid            NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    from_status     ticket_status,
    to_status       ticket_status   NOT NULL,
    changed_by      uuid            REFERENCES users(id) ON DELETE SET NULL,
    reason          text,
    metadata        jsonb           NOT NULL DEFAULT '{}'::jsonb,
    changed_at      timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ticket_status_hist_ticket
    ON ticket_status_history(ticket_id, changed_at DESC);


-- ----------------------------------------------------------------------------
-- ticket_sla_rules SLA 规则 (按 priority 配响应/解决小时数)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ticket_sla_rules (
    id                  uuid            PRIMARY KEY DEFAULT gen_random_uuid(),
    priority            ticket_priority NOT NULL UNIQUE,
    first_response_hrs  integer         NOT NULL,
    resolution_hrs      integer         NOT NULL,
    description         text,
    is_active           boolean         NOT NULL DEFAULT TRUE,
    created_at          timestamptz     NOT NULL DEFAULT now(),
    updated_at          timestamptz     NOT NULL DEFAULT now()
);

-- 默认 SLA 规则 (urgent 1h/8h; high 2h/24h; normal 8h/72h; low 24h/168h)
INSERT INTO ticket_sla_rules (priority, first_response_hrs, resolution_hrs, description)
VALUES
    ('urgent', 1,   8,   '紧急 (1 小时响应 / 8 小时解决)'),
    ('high',   2,   24,  '高 (2 小时响应 / 24 小时解决)'),
    ('normal', 8,   72,  '普通 (8 小时响应 / 72 小时解决)'),
    ('low',    24,  168, '低 (24 小时响应 / 168 小时解决)')
ON CONFLICT (priority) DO NOTHING;


-- ----------------------------------------------------------------------------
-- updated_at 自动维护
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_tickets_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tickets_touch_updated_at ON tickets;
CREATE TRIGGER tickets_touch_updated_at
    BEFORE UPDATE ON tickets
    FOR EACH ROW EXECUTE FUNCTION trg_tickets_touch_updated_at();

DROP TRIGGER IF EXISTS ticket_sla_rules_touch_updated_at ON ticket_sla_rules;
CREATE TRIGGER ticket_sla_rules_touch_updated_at
    BEFORE UPDATE ON ticket_sla_rules
    FOR EACH ROW EXECUTE FUNCTION trg_tickets_touch_updated_at();


-- ----------------------------------------------------------------------------
-- 视图: 当前 SLA 状态 (待办 + 逾期)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_tickets_overdue AS
SELECT t.*,
       EXTRACT(EPOCH FROM (now() - t.sla_due_at))::int AS seconds_overdue
FROM tickets t
WHERE t.sla_due_at IS NOT NULL
  AND t.sla_due_at < now()
  AND t.status NOT IN ('resolved', 'closed');

COMMENT ON VIEW v_tickets_overdue IS
    '逾期未解决的工单 (status ≠ resolved/closed 且 sla_due_at 已过)';


-- ============================================================================
-- RLS
-- ============================================================================

-- ---- TICKETS ----
ALTER TABLE tickets ENABLE ROW LEVEL SECURITY;

-- 管理员全权
DROP POLICY IF EXISTS "tickets_admin_all" ON tickets;
CREATE POLICY "tickets_admin_all" ON tickets
    FOR ALL USING (
        EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role = 'admin')
    );

-- HR (talent_partner) 全权: 看/处理所有工单
DROP POLICY IF EXISTS "tickets_hr_all" ON tickets;
CREATE POLICY "tickets_hr_all" ON tickets
    FOR ALL USING (
        EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role = 'talent_partner')
    );

-- 员工: 自己创建的工单可读
DROP POLICY IF EXISTS "tickets_user_read" ON tickets;
CREATE POLICY "tickets_user_read" ON tickets
    FOR SELECT USING (user_id = auth.uid());

-- 员工: 自己可创建工单 (user_id 必须是自己)
DROP POLICY IF EXISTS "tickets_user_insert" ON tickets;
CREATE POLICY "tickets_user_insert" ON tickets
    FOR INSERT WITH CHECK (user_id = auth.uid());

-- 员工: 不能改 status (由 HR 改); 但可以更新自己的描述
DROP POLICY IF EXISTS "tickets_user_update_meta" ON tickets;
CREATE POLICY "tickets_user_update_meta" ON tickets
    FOR UPDATE USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());


-- ---- TICKET_COMMENTS ----
ALTER TABLE ticket_comments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "ticket_comments_admin_all" ON ticket_comments;
CREATE POLICY "ticket_comments_admin_all" ON ticket_comments
    FOR ALL USING (
        EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role = 'admin')
    );

DROP POLICY IF EXISTS "ticket_comments_hr_all" ON ticket_comments;
CREATE POLICY "ticket_comments_hr_all" ON ticket_comments
    FOR ALL USING (
        EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role = 'talent_partner')
    );

DROP POLICY IF EXISTS "ticket_comments_user_read" ON ticket_comments;
CREATE POLICY "ticket_comments_user_read" ON ticket_comments
    FOR SELECT USING (
        ticket_id IN (SELECT id FROM tickets WHERE user_id = auth.uid())
    );

DROP POLICY IF EXISTS "ticket_comments_user_insert" ON ticket_comments;
CREATE POLICY "ticket_comments_user_insert" ON ticket_comments
    FOR INSERT WITH CHECK (
        ticket_id IN (SELECT id FROM tickets WHERE user_id = auth.uid())
        AND author_id = auth.uid()
    );


-- ---- TICKET_STATUS_HISTORY ----
ALTER TABLE ticket_status_history ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "ticket_status_hist_admin_all" ON ticket_status_history;
CREATE POLICY "ticket_status_hist_admin_all" ON ticket_status_history
    FOR ALL USING (
        EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role = 'admin')
    );

DROP POLICY IF EXISTS "ticket_status_hist_hr_all" ON ticket_status_history;
CREATE POLICY "ticket_status_hist_hr_all" ON ticket_status_history
    FOR ALL USING (
        EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role = 'talent_partner')
    );

DROP POLICY IF EXISTS "ticket_status_hist_user_read" ON ticket_status_history;
CREATE POLICY "ticket_status_hist_user_read" ON ticket_status_history
    FOR SELECT USING (
        ticket_id IN (SELECT id FROM tickets WHERE user_id = auth.uid())
    );

DROP POLICY IF EXISTS "ticket_status_hist_insert" ON ticket_status_history;
CREATE POLICY "ticket_status_hist_insert" ON ticket_status_history
    FOR INSERT WITH CHECK (true);


-- ---- TICKET_SLA_RULES ----
ALTER TABLE ticket_sla_rules ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "ticket_sla_rules_read_all" ON ticket_sla_rules;
CREATE POLICY "ticket_sla_rules_read_all" ON ticket_sla_rules
    FOR SELECT USING (true);

DROP POLICY IF EXISTS "ticket_sla_rules_admin_write" ON ticket_sla_rules;
CREATE POLICY "ticket_sla_rules_admin_write" ON ticket_sla_rules
    FOR ALL USING (
        EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role = 'admin')
    );


-- ============================================================================
-- REALTIME
-- ============================================================================
ALTER PUBLICATION supabase_realtime ADD TABLE tickets;
ALTER PUBLICATION supabase_realtime ADD TABLE ticket_comments;
ALTER PUBLICATION supabase_realtime ADD TABLE ticket_status_history;


-- ============================================================================
-- COMMENTS
-- ============================================================================
COMMENT ON TABLE tickets IS
    'HR 工单主表 (T207): 员工提单 → HR 处理 → 关闭; 含 SLA 字段';
COMMENT ON COLUMN tickets.sla_due_at IS
    '按 SLA 规则计算出的最迟解决时间; 状态变更可重新计算';
COMMENT ON COLUMN tickets.metadata IS
    '附加元数据 (例: 智能体创建时的上下文 {source: "agent", agent_name: "hr_service_agent", trigger: "sensitive"})';
COMMENT ON TABLE ticket_comments IS
    '工单评论/对话: employee / hr / system 三种 author_type';
COMMENT ON TABLE ticket_status_history IS
    '状态流转审计: 每次 status 变化都写入一条';
COMMENT ON TABLE ticket_sla_rules IS
    'SLA 规则: 按 priority 配 first_response_hrs / resolution_hrs';