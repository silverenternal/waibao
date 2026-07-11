-- ============================================================================
-- 012_persona_preferences.sql
-- Persona 偏好记忆表 (T703)
--
-- 设计要点:
-- 1. persona_prefs 表 — 长期存储老板 (employer / hr / boss) 的偏好:
--    communication_style (正式/直接/温和) / preferred_terms / decision_patterns /
--    time_zone / favorite_meeting_time
-- 2. 每条 (user_id, organisation_id, pref_key) 唯一;带 source (explicit / inferred)
--    和 confidence (0..1) 字段,允许自动学习时只接受高置信度的偏好。
-- 3. RLS: 自己的偏好可读/写;HR 同 org 可读;admin 全部。
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1) persona_prefs 表
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS persona_prefs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    organisation_id uuid REFERENCES organisations(id) ON DELETE CASCADE,

    pref_key        text NOT NULL,         -- communication_style | preferred_terms | decision_patterns | time_zone | favorite_meeting_time | ...
    pref_value      jsonb NOT NULL,        -- {"value": "...", "examples": [...], "tags": [...]}

    source          text NOT NULL DEFAULT 'explicit',  -- explicit | inferred | admin
    confidence      double precision NOT NULL DEFAULT 0.7 CHECK (confidence >= 0 AND confidence <= 1),

    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    UNIQUE (user_id, organisation_id, pref_key)
);

CREATE INDEX IF NOT EXISTS idx_persona_prefs_user
    ON persona_prefs (user_id, organisation_id);

CREATE INDEX IF NOT EXISTS idx_persona_prefs_key
    ON persona_prefs (pref_key);

CREATE INDEX IF NOT EXISTS idx_persona_prefs_confidence
    ON persona_prefs (confidence) WHERE confidence >= 0.5;


-- ----------------------------------------------------------------------------
-- 2) updated_at 自动维护
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_persona_prefs_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS persona_prefs_updated_at ON persona_prefs;
CREATE TRIGGER persona_prefs_updated_at
    BEFORE UPDATE ON persona_prefs
    FOR EACH ROW EXECUTE FUNCTION trg_persona_prefs_updated_at();


-- ----------------------------------------------------------------------------
-- 3) RLS
-- ----------------------------------------------------------------------------
ALTER TABLE persona_prefs ENABLE ROW LEVEL SECURITY;

-- 3.1 自己的偏好: 读 + 写
DROP POLICY IF EXISTS persona_prefs_self_rw ON persona_prefs;
CREATE POLICY persona_prefs_self_rw ON persona_prefs
    FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- 3.2 同 org HR 可读 (辅助协作)
DROP POLICY IF EXISTS persona_prefs_hr_read ON persona_prefs;
CREATE POLICY persona_prefs_hr_read ON persona_prefs
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM org_members om
            WHERE om.organisation_id = persona_prefs.organisation_id
              AND om.user_id = auth.uid()
              AND om.role IN ('hr', 'admin', 'dept_head')
        )
    );

-- 3.3 admin 全权限
DROP POLICY IF EXISTS persona_prefs_admin ON persona_prefs;
CREATE POLICY persona_prefs_admin ON persona_prefs
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM users u
            WHERE u.id = auth.uid() AND u.role = 'admin'
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM users u
            WHERE u.id = auth.uid() AND u.role = 'admin'
        )
    );


-- ----------------------------------------------------------------------------
-- 4) service_role bypass
-- ----------------------------------------------------------------------------
-- 注释: supabase service_role key 会自动绕过 RLS,适合后端写入