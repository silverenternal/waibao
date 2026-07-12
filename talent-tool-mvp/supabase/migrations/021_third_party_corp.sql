-- ============================================================
-- Migration 021: Third-party corp (DingTalk / Feishu) bindings — T1204
-- 与 backend/services/corp_sync.py 协作
-- 支持:
--   1. 企业绑定表 (钉钉 / 飞书 / WeCom ...)
--   2. 用户映射 (external_user_id -> internal_user_id)
--   3. 角色自动映射规则 (boss / HR / dept_head / employee)
-- ============================================================

-- ------------------------------------------------------------
-- 企业绑定表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS corp_bindings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    corp_id             VARCHAR(128) NOT NULL,          -- 钉钉 corpId / 飞书 tenant_key
    corp_type           VARCHAR(32)  NOT NULL,           -- 'dingtalk' | 'feishu' | 'wecom'
    corp_name           VARCHAR(256) NOT NULL,
    suite_id            VARCHAR(128),                   -- 钉钉 suite / 飞书 app_id
    agent_id            VARCHAR(128),                   -- 钉钉 AgentID / 飞书 AppID
    access_token        TEXT,                           -- 加密存储
    refresh_token       TEXT,
    token_expires_at    TIMESTAMPTZ,
    webhook_url         TEXT,                           -- 默认群机器人 webhook
    webhook_secret      TEXT,                           -- 群机器人签名 secret
    sync_state          JSONB NOT NULL DEFAULT '{}'::JSONB,  -- 最近一次同步结果
    auto_role_mapping   JSONB NOT NULL DEFAULT '{}'::JSONB,  -- 角色自动映射规则
    approval_template_id VARCHAR(128),                  -- 工单审批流模板 ID
    status              VARCHAR(16) NOT NULL DEFAULT 'active',  -- active/disabled
    activated_at        TIMESTAMPTZ DEFAULT NOW(),
    last_synced_at      TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (corp_id, corp_type)
);

CREATE INDEX IF NOT EXISTS idx_corp_bindings_type ON corp_bindings(corp_type);
CREATE INDEX IF NOT EXISTS idx_corp_bindings_status ON corp_bindings(status);

-- ------------------------------------------------------------
-- 用户映射表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS corp_user_mappings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    binding_id          UUID NOT NULL REFERENCES corp_bindings(id) ON DELETE CASCADE,
    external_user_id    VARCHAR(128) NOT NULL,           -- 钉钉 userid / 飞书 open_id
    external_union_id   VARCHAR(128),                   -- 钉钉 unionid / 飞书 union_id
    external_dept_ids   TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],  -- 所在部门 ID 列表
    internal_user_id    UUID,                           -- waibao.users.id
    role                VARCHAR(32) NOT NULL DEFAULT 'employee',  -- boss/hr/dept_head/employee
    name                VARCHAR(128),
    mobile              VARCHAR(32),
    email               VARCHAR(128),
    title               VARCHAR(128),                   -- 职位
    is_admin            BOOLEAN NOT NULL DEFAULT FALSE,
    is_boss             BOOLEAN NOT NULL DEFAULT FALSE,
    is_hr               BOOLEAN NOT NULL DEFAULT FALSE,
    is_dept_head        BOOLEAN NOT NULL DEFAULT FALSE,
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (binding_id, external_user_id)
);

CREATE INDEX IF NOT EXISTS idx_corp_users_internal ON corp_user_mappings(internal_user_id);
CREATE INDEX IF NOT EXISTS idx_corp_users_role ON corp_user_mappings(role);
CREATE INDEX IF NOT EXISTS idx_corp_users_external_union ON corp_user_mappings(external_union_id);

-- ------------------------------------------------------------
-- 同步审计日志 (用于追踪准确率/失败原因)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS corp_sync_logs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    binding_id          UUID NOT NULL REFERENCES corp_bindings(id) ON DELETE CASCADE,
    sync_type           VARCHAR(32) NOT NULL,           -- 'dept' / 'user' / 'role' / 'approval'
    direction           VARCHAR(16) NOT NULL,           -- 'pull' / 'push'
    status              VARCHAR(16) NOT NULL,           -- 'success' / 'partial' / 'failed'
    total               INTEGER NOT NULL DEFAULT 0,
    succeeded           INTEGER NOT NULL DEFAULT 0,
    failed              INTEGER NOT NULL DEFAULT 0,
    error               TEXT,
    payload             JSONB,
    duration_ms         INTEGER,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_corp_sync_binding ON corp_sync_logs(binding_id);
CREATE INDEX IF NOT EXISTS idx_corp_sync_synced_at ON corp_sync_logs(synced_at DESC);

-- ------------------------------------------------------------
-- 审批实例表 (工单 → 第三方审批映射)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS corp_approval_instances (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    binding_id          UUID NOT NULL REFERENCES corp_bindings(id) ON DELETE CASCADE,
    ticket_id           UUID,                           -- waibao tickets.id
    external_instance_id VARCHAR(128) NOT NULL,         -- 钉钉 process_instance_id / 飞书 instance_id
    template_id         VARCHAR(128) NOT NULL,
    form_data           JSONB NOT NULL DEFAULT '{}'::JSONB,
    status              VARCHAR(32) NOT NULL DEFAULT 'pending',  -- pending/approved/rejected/canceled
    approver_external_id VARCHAR(128),
    synced_to_ticket    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (binding_id, external_instance_id)
);

CREATE INDEX IF NOT EXISTS idx_corp_approval_ticket ON corp_approval_instances(ticket_id);
CREATE INDEX IF NOT EXISTS idx_corp_approval_status ON corp_approval_instances(status);

-- ------------------------------------------------------------
-- updated_at 触发器
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_corp_bindings_touch()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tg_corp_bindings_touch ON corp_bindings;
CREATE TRIGGER tg_corp_bindings_touch
    BEFORE UPDATE ON corp_bindings
    FOR EACH ROW EXECUTE FUNCTION trg_corp_bindings_touch();

DROP TRIGGER IF EXISTS tg_corp_users_touch ON corp_user_mappings;
CREATE TRIGGER tg_corp_users_touch
    BEFORE UPDATE ON corp_user_mappings
    FOR EACH ROW EXECUTE FUNCTION trg_corp_bindings_touch();

DROP TRIGGER IF EXISTS tg_corp_approval_touch ON corp_approval_instances;
CREATE TRIGGER tg_corp_approval_touch
    BEFORE UPDATE ON corp_approval_instances
    FOR EACH ROW EXECUTE FUNCTION trg_corp_bindings_touch();

-- ------------------------------------------------------------
-- RLS (默认开启; 管理员绕过)
-- ------------------------------------------------------------
ALTER TABLE corp_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE corp_user_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE corp_sync_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE corp_approval_instances ENABLE ROW LEVEL SECURITY;

-- 只允许 service_role 访问 (服务端 API 统一管理)
DROP POLICY IF EXISTS corp_bindings_svc ON corp_bindings;
CREATE POLICY corp_bindings_svc ON corp_bindings FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS corp_users_svc ON corp_user_mappings;
CREATE POLICY corp_users_svc ON corp_user_mappings FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS corp_sync_logs_svc ON corp_sync_logs;
CREATE POLICY corp_sync_logs_svc ON corp_sync_logs FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS corp_approval_svc ON corp_approval_instances;
CREATE POLICY corp_approval_svc ON corp_approval_instances FOR ALL TO service_role USING (true) WITH CHECK (true);