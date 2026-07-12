-- T2301 — saved_comparisons 表
-- 用户保存的对比快照 (候选人对比 / 岗位对比)

CREATE TABLE IF NOT EXISTS saved_comparisons (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    item_type TEXT NOT NULL CHECK (item_type IN ('candidate', 'role')),
    item_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    title TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_saved_comparisons_user
    ON saved_comparisons(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_saved_comparisons_type
    ON saved_comparisons(item_type, created_at DESC);

-- updated_at 自动维护
CREATE OR REPLACE FUNCTION saved_comparisons_touch_updated()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_saved_comparisons_updated ON saved_comparisons;
CREATE TRIGGER trg_saved_comparisons_updated
    BEFORE UPDATE ON saved_comparisons
    FOR EACH ROW
    EXECUTE FUNCTION saved_comparisons_touch_updated();

-- RLS
ALTER TABLE saved_comparisons ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS saved_comparisons_owner ON saved_comparisons;
CREATE POLICY saved_comparisons_owner ON saved_comparisons
    FOR ALL TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS saved_comparisons_admin ON saved_comparisons;
CREATE POLICY saved_comparisons_admin ON saved_comparisons
    FOR ALL TO authenticated
    USING (auth.user_role() = 'admin')
    WITH CHECK (auth.user_role() = 'admin');

COMMENT ON TABLE saved_comparisons IS 'T2301 用户保存的候选人/岗位对比快照';
COMMENT ON COLUMN saved_comparisons.item_ids IS '被对比的候选人或岗位 ID 数组';
COMMENT ON COLUMN saved_comparisons.payload IS '完整 DiffResult JSON 快照';