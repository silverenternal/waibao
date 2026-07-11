-- ============================================================================
-- 009_notify_prefs.sql
-- 用户通知偏好表 (T104)
--
-- 设计要点:
-- 1. 每 (user_id, channel, category) 一行 (主键):
--    - channel: smtp / dingtalk / feishu / wecom / webhook / web
--    - category: 业务类别 emotion_high_risk / ticket_created / match_success / system_alert
--    - enabled: 用户是否开启该通道 + 类别的接收
-- 2. 默认行为: 用户未配置时默认全部启用 (由 dispatcher 侧兜底).
-- 3. 管理员可针对单一用户批量开关 (通过 channel='*' 语义或 admin API 全局覆盖).
-- 4. 支持 RLS: 用户本人可读写; admin 可全权.
-- ============================================================================

-- 通知通道枚举
DO $$ BEGIN
    CREATE TYPE notify_channel AS ENUM (
        'smtp',
        'dingtalk',
        'feishu',
        'wecom',
        'webhook',
        'web'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- 业务类别枚举
DO $$ BEGIN
    CREATE TYPE notify_category AS ENUM (
        'emotion_high_risk',
        'ticket_created',
        'match_success',
        'system_alert'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS notify_preferences (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel         notify_channel NOT NULL,
    category        notify_category NOT NULL,
    enabled         boolean     NOT NULL DEFAULT TRUE,
    -- 渠道级细节 (例如 at_mobiles,email override),jsonb
    channel_config  jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    -- 同一用户同一 channel+category 只能有一条
    CONSTRAINT uq_notify_prefs UNIQUE (user_id, channel, category)
);

-- 索引 (admin 批量查询 / 单用户聚合)
CREATE INDEX IF NOT EXISTS idx_notify_prefs_user
    ON notify_preferences(user_id);

CREATE INDEX IF NOT EXISTS idx_notify_prefs_channel
    ON notify_preferences(channel)
    WHERE enabled = TRUE;

-- updated_at 自动维护
CREATE OR REPLACE FUNCTION trg_notify_prefs_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS notify_prefs_touch_updated_at ON notify_preferences;
CREATE TRIGGER notify_prefs_touch_updated_at
    BEFORE UPDATE ON notify_preferences
    FOR EACH ROW EXECUTE FUNCTION trg_notify_prefs_touch_updated_at();

-- ============================================================================
-- RLS
-- ============================================================================
ALTER TABLE notify_preferences ENABLE ROW LEVEL SECURITY;

-- 用户可读取自己的偏好
DROP POLICY IF EXISTS "notify_prefs_self_read" ON notify_preferences;
CREATE POLICY "notify_prefs_self_read" ON notify_preferences
    FOR SELECT USING (auth.uid() = user_id);

-- 用户可写入自己的偏好 (UPSERT)
DROP POLICY IF EXISTS "notify_prefs_self_write" ON notify_preferences;
CREATE POLICY "notify_prefs_self_write" ON notify_preferences
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "notify_prefs_self_update" ON notify_preferences;
CREATE POLICY "notify_prefs_self_update" ON notify_preferences
    FOR UPDATE USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "notify_prefs_self_delete" ON notify_preferences;
CREATE POLICY "notify_prefs_self_delete" ON notify_preferences
    FOR DELETE USING (auth.uid() = user_id);

-- 管理员全权
DROP POLICY IF EXISTS "notify_prefs_admin_all" ON notify_preferences;
CREATE POLICY "notify_prefs_admin_all" ON notify_preferences
    FOR ALL USING (
        EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role = 'admin')
    );

-- ============================================================================
-- 视图: 按用户聚合开启的通道 (dispatcher 偏好查询优化)
-- ============================================================================
CREATE OR REPLACE VIEW v_user_enabled_channels AS
SELECT user_id, category, array_agg(channel::text) AS channels
FROM notify_preferences
WHERE enabled = TRUE
GROUP BY user_id, category;

COMMENT ON TABLE notify_preferences IS
    '用户通知偏好 (T104): 每 (user, channel, category) 控制是否接收';
COMMENT ON COLUMN notify_preferences.channel_config IS
    '通道级配置 (jsonb): 覆盖默认收件人/atMobiles/webhook URL 等';
COMMENT ON VIEW v_user_enabled_channels IS
    'dispatcher 用视图: 按用户 + 类别返回开启的通道列表';