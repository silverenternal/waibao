-- ============================================================
-- Migration 002: Agent 记忆表
-- 支持智能体三层记忆 (short_term/working/long_term)
-- ============================================================

CREATE TABLE IF NOT EXISTS agent_memory (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL,
    persona     TEXT NOT NULL,
    scope       TEXT NOT NULL CHECK (scope IN ('short_term', 'working', 'long_term')),
    key         TEXT NOT NULL,
    value       JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    expires_at  TIMESTAMPTZ,
    UNIQUE (user_id, scope, key)
);

CREATE INDEX IF NOT EXISTS idx_agent_memory_user_scope
    ON agent_memory (user_id, scope);

CREATE INDEX IF NOT EXISTS idx_agent_memory_expires
    ON agent_memory (expires_at)
    WHERE expires_at IS NOT NULL;

-- RLS: 用户只能访问自己的记忆
ALTER TABLE agent_memory ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users access own memory" ON agent_memory
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- 管理员可访问所有
CREATE POLICY "Admins access all memory" ON agent_memory
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM users
            WHERE users.id = auth.uid()
              AND users.role = 'admin'
        )
    );

-- 自动清理过期记忆
CREATE OR REPLACE FUNCTION cleanup_expired_memory()
RETURNS void AS $$
BEGIN
    DELETE FROM agent_memory
    WHERE expires_at IS NOT NULL AND expires_at < NOW();
END;
$$ LANGUAGE plpgsql;