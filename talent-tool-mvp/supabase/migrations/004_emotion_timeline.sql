-- ============================================================
-- Migration 004: 求职者情绪时间线
-- ============================================================

CREATE TABLE IF NOT EXISTS emotion_timeline (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    recorded_at     TIMESTAMPTZ DEFAULT NOW(),
    primary_emotion TEXT NOT NULL,                   -- joy/sadness/anger/fear/surprise/disgust/neutral
    intensity       NUMERIC(3,2) NOT NULL,           -- 0.0 ~ 1.0
    sentiment       NUMERIC(3,2) NOT NULL,           -- -1.0 ~ 1.0
    trigger_text    TEXT,                            -- 触发该情绪的原文片段
    context         JSONB DEFAULT '{}'::jsonb,      -- 当时场景
    needs_attention BOOLEAN DEFAULT FALSE,           -- 是否需要人工介入
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_emotion_timeline_user_time
    ON emotion_timeline (user_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_emotion_timeline_alerts
    ON emotion_timeline (user_id, needs_attention)
    WHERE needs_attention = TRUE;

ALTER TABLE emotion_timeline ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users access own emotion" ON emotion_timeline
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Admins access all emotion" ON emotion_timeline
    FOR ALL
    USING (EXISTS (SELECT 1 FROM users WHERE users.id = auth.uid() AND users.role = 'admin'));

-- 情绪告警视图: 连续3次 negative 标记 needs_attention
CREATE OR REPLACE VIEW emotion_alerts AS
SELECT user_id, COUNT(*) as negative_streak, MIN(recorded_at) as since
FROM emotion_timeline
WHERE sentiment < -0.3
  AND recorded_at > NOW() - INTERVAL '7 days'
GROUP BY user_id
HAVING COUNT(*) >= 3;