-- ============================================================
-- Migration 003: 对话历史表 (带情绪标签)
-- ============================================================

CREATE TABLE IF NOT EXISTS conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    persona         TEXT NOT NULL,
    agent_name      TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('user', 'agent', 'system')),
    content         TEXT NOT NULL,
    emotion         TEXT,                          -- joy/sadness/anger/fear/surprise/neutral
    emotion_score   NUMERIC(3,2),                  -- -1.0 ~ 1.0
    intent          TEXT,                          -- chitchat/query/feedback/complaint
    artifacts       JSONB DEFAULT '{}'::jsonb,     -- 结构化产物
    signal_event_id UUID,                          -- 关联 signal
    trace_id        TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_time
    ON conversations (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_conversations_emotion
    ON conversations (user_id, emotion)
    WHERE emotion IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_conversations_trace
    ON conversations (trace_id)
    WHERE trace_id IS NOT NULL;

ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users access own conversations" ON conversations
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Admins access all conversations" ON conversations
    FOR ALL
    USING (
        EXISTS (SELECT 1 FROM users WHERE users.id = auth.uid() AND users.role = 'admin')
    );