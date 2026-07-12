-- ============================================================================
-- 041_notification_prefs.sql
-- 智能通知偏好 (T2304)
--
-- 在 T104 ``notify_preferences`` 基础上扩展:
-- 1. ``notification_prefs`` —— 用户细粒度偏好 (category × priority × channel + frequency)
-- 2. ``notification_digest``  —— 定期摘要记录 (小时/天/周)
-- 3. ``smart_suggestions``   —— LLM 生成的智能优化建议
-- 4. ``notification_log``    —— 通知发送日志 (用于智能降噪: 5 分钟同 category 仅一次)
--
-- 设计要点:
-- - 与 ``notify_preferences`` 共存: 旧表是布尔开关, 新表存储频率/静默时间/优先级等细粒度字段.
-- - frequency: realtime / hourly / daily / weekly
-- - quiet_hours: tstzrange 表示跨午夜的范围, 例如 [22:00, 08:00)
-- - priority_filter: array of allowed priorities (low/medium/high/urgent)
-- - RLS: 用户可读写自己的 prefs/suggestions; admin 全权.
-- ============================================================================


-- ---------------------------------------------------------------------------
-- 1. notification_prefs (细粒度偏好)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS notification_prefs (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- category: matching / ticket / emotion / system / recruiting
    category        text        NOT NULL,
    -- priority: high / medium / low (low 不重要通知)
    priority        text        NOT NULL DEFAULT 'medium',

    -- channel: smtp / dingtalk / feishu / im / web
    channel         text        NOT NULL,

    -- frequency: realtime / hourly / daily / weekly
    frequency       text        NOT NULL DEFAULT 'realtime',

    -- 静默时间 (用户本地时区, 存为 HH:MM 字符串; 处理跨午夜例如 22:00-08:00)
    quiet_hours_start   text,
    quiet_hours_end     text,

    -- 是否启用
    enabled         boolean     NOT NULL DEFAULT TRUE,

    -- 时间戳
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_notification_prefs UNIQUE (user_id, category, priority, channel)
);

CREATE INDEX IF NOT EXISTS idx_notification_prefs_user
    ON notification_prefs(user_id);

CREATE INDEX IF NOT EXISTS idx_notification_prefs_lookup
    ON notification_prefs(user_id, category, priority, channel)
    WHERE enabled = TRUE;

-- updated_at 触发器
CREATE OR REPLACE FUNCTION trg_notification_prefs_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS notification_prefs_touch_updated_at ON notification_prefs;
CREATE TRIGGER notification_prefs_touch_updated_at
    BEFORE UPDATE ON notification_prefs
    FOR EACH ROW EXECUTE FUNCTION trg_notification_prefs_touch_updated_at();

COMMENT ON TABLE notification_prefs IS
    'T2304 智能通知偏好: category × priority × channel × frequency + 静默时间';


-- ---------------------------------------------------------------------------
-- 2. notification_digest (定期摘要记录)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS notification_digest (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- period: hourly / daily / weekly
    period          text        NOT NULL,
    -- digest 内容 (jsonb, 含通知列表 + 统计)
    content         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    -- 该摘要涵盖的时间窗 (UTC)
    window_start    timestamptz NOT NULL,
    window_end      timestamptz NOT NULL,

    sent_at         timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_digest_period CHECK (period IN ('hourly', 'daily', 'weekly'))
);

CREATE INDEX IF NOT EXISTS idx_notification_digest_user_time
    ON notification_digest(user_id, sent_at DESC);

CREATE INDEX IF NOT EXISTS idx_notification_digest_period_time
    ON notification_digest(period, sent_at DESC);

COMMENT ON TABLE notification_digest IS
    'T2304 定期摘要记录: 用户偏好的 hourly/daily/weekly 摘要';


-- ---------------------------------------------------------------------------
-- 3. smart_suggestions (LLM 智能建议)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS smart_suggestions (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- suggestion 类型: priority_reduce / category_disable / channel_change / frequency_change / quiet_hours_extend
    type            text        NOT NULL,
    -- 建议人类可读文本 (中文/英文皆可)
    description     text        NOT NULL,
    -- 建议的可执行 patch (例如 {category: ticket, priority: medium})
    suggestion      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    -- LLM 给出的置信度 0-1
    confidence      real        NOT NULL DEFAULT 0.5,
    -- 状态: pending / applied / dismissed
    status          text        NOT NULL DEFAULT 'pending',
    -- 依据 (jsonb: 7 天使用分析的数据快照)
    based_on        jsonb       NOT NULL DEFAULT '{}'::jsonb,

    created_at      timestamptz NOT NULL DEFAULT now(),
    applied_at      timestamptz,
    dismissed_at    timestamptz,

    CONSTRAINT chk_suggestion_status CHECK (status IN ('pending', 'applied', 'dismissed'))
);

CREATE INDEX IF NOT EXISTS idx_smart_suggestions_user_pending
    ON smart_suggestions(user_id, created_at DESC)
    WHERE status = 'pending';

COMMENT ON TABLE smart_suggestions IS
    'T2304 LLM 生成的智能通知优化建议 (基于 7 天使用分析)';


-- ---------------------------------------------------------------------------
-- 4. notification_log (发送日志 — 用于 5 分钟降噪 + 使用分析)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS notification_log (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid        NOT NULL,
    category        text        NOT NULL,
    priority        text        NOT NULL DEFAULT 'medium',
    channel         text        NOT NULL,
    -- 是否被降噪过滤 (5 分钟内重复)
    throttled       boolean     NOT NULL DEFAULT FALSE,
    -- 是否处于静默时间
    quiet_hours_hit boolean     NOT NULL DEFAULT FALSE,
    sent_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notification_log_throttle
    ON notification_log(user_id, category, channel, sent_at DESC);

CREATE INDEX IF NOT EXISTS idx_notification_log_user_time
    ON notification_log(user_id, sent_at DESC)
    WHERE throttled = FALSE;

COMMENT ON TABLE notification_log IS
    'T2304 通知发送日志 (降噪 + 智能分析数据源)';


-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------

ALTER TABLE notification_prefs    ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_digest   ENABLE ROW LEVEL SECURITY;
ALTER TABLE smart_suggestions     ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_log      ENABLE ROW LEVEL SECURITY;

-- notification_prefs: 用户可读写
DROP POLICY IF EXISTS "notification_prefs_self_all" ON notification_prefs;
CREATE POLICY "notification_prefs_self_all" ON notification_prefs
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "notification_prefs_admin_all" ON notification_prefs;
CREATE POLICY "notification_prefs_admin_all" ON notification_prefs
    FOR ALL USING (
        EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role = 'admin')
    );

-- notification_digest: 用户只读自己的 (后台写入)
DROP POLICY IF EXISTS "notification_digest_self_read" ON notification_digest;
CREATE POLICY "notification_digest_self_read" ON notification_digest
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "notification_digest_admin_all" ON notification_digest;
CREATE POLICY "notification_digest_admin_all" ON notification_digest
    FOR ALL USING (
        EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role = 'admin')
    );

-- smart_suggestions: 用户可读 + 更新状态; 后台写入
DROP POLICY IF EXISTS "smart_suggestions_self_read" ON smart_suggestions;
CREATE POLICY "smart_suggestions_self_read" ON smart_suggestions
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "smart_suggestions_self_update" ON smart_suggestions;
CREATE POLICY "smart_suggestions_self_update" ON smart_suggestions
    FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "smart_suggestions_admin_all" ON smart_suggestions;
CREATE POLICY "smart_suggestions_admin_all" ON smart_suggestions
    FOR ALL USING (
        EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role = 'admin')
    );

-- notification_log: 用户只读自己的 (后台写入; 仅 admin 可写)
DROP POLICY IF EXISTS "notification_log_self_read" ON notification_log;
CREATE POLICY "notification_log_self_read" ON notification_log
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "notification_log_admin_all" ON notification_log;
CREATE POLICY "notification_log_admin_all" ON notification_log
    FOR ALL USING (
        EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role = 'admin')
    );