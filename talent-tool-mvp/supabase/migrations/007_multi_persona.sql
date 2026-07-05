-- ============================================================
-- Migration 007: 多 Persona 支持
-- ============================================================

-- 用户-多 persona 关联
CREATE TABLE IF NOT EXISTS user_personas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    persona         TEXT NOT NULL CHECK (persona IN (
        'jobseeker', 'boss', 'hr', 'dept_head', 'admin'
    )),
    organisation_id UUID,                          -- 该 persona 所属组织
    is_primary      BOOLEAN DEFAULT FALSE,         -- 是否默认 persona
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, persona, organisation_id)
);

CREATE INDEX IF NOT EXISTS idx_user_personas_user
    ON user_personas (user_id);

CREATE INDEX IF NOT EXISTS idx_user_personas_org
    ON user_personas (organisation_id);

-- 每个用户最多 1 个主 persona
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_personas_one_primary
    ON user_personas (user_id) WHERE is_primary = TRUE;

ALTER TABLE user_personas ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see own personas" ON user_personas
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Admins manage all personas" ON user_personas
    FOR ALL USING (
        EXISTS (SELECT 1 FROM users WHERE users.id = auth.uid() AND users.role = 'admin')
    );

-- 组织成员互见(便于协作)
CREATE POLICY "Org members see each other personas" ON user_personas
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM user_personas up2
            WHERE up2.user_id = auth.uid()
              AND up2.organisation_id = user_personas.organisation_id
        )
    );

-- 触发器: 每个用户的第一个 persona 自动设为 primary
CREATE OR REPLACE FUNCTION set_first_persona_primary()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM user_personas WHERE user_id = NEW.user_id AND is_primary = TRUE
    ) THEN
        NEW.is_primary := TRUE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_set_first_persona_primary
    BEFORE INSERT ON user_personas
    FOR EACH ROW EXECUTE FUNCTION set_first_persona_primary();