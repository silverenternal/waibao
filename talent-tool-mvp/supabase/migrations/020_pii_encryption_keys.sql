-- ============================================================
-- Migration 020: PII 加密密钥轮转表 — T1202
-- 与 backend/services/pii_field_encryption.py 协作
-- 支持:
--   1. 多代密钥并存(老 token 仍可解密)
--   2. 轮转记录(audit)
--   3. 密钥级别(L2/L3/L4)分别加密
-- ============================================================

-- pgcrypto 扩展(cryptography 库的 SQL 等价)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 字段级密钥表
-- 一行 = 一代密钥(版本号自增)
CREATE TABLE IF NOT EXISTS pii_encryption_keys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    field_name      VARCHAR(64) NOT NULL,
    key_version     INTEGER NOT NULL,
    key_level       SMALLINT NOT NULL DEFAULT 2,  -- 1/2/3/4
    encrypted_key   TEXT NOT NULL,                  -- KMS-wrapped,base64
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    rotated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rotated_by      UUID,
    expires_at      TIMESTAMPTZ,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (field_name, key_version)
);

CREATE INDEX IF NOT EXISTS idx_pii_keys_field_active
    ON pii_encryption_keys(field_name, is_active);

-- 密钥轮转审计表
CREATE TABLE IF NOT EXISTS pii_key_rotation_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    field_name      VARCHAR(64) NOT NULL,
    old_version     INTEGER,
    new_version     INTEGER NOT NULL,
    rotated_by      UUID,
    rotated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rows_re_encrypted INTEGER DEFAULT 0,
    notes           TEXT
);

-- 加密字段清单表(供服务启动时自动加载)
CREATE TABLE IF NOT EXISTS pii_field_registry (
    field_name      VARCHAR(64) PRIMARY KEY,
    field_level     SMALLINT NOT NULL,           -- 2/3/4
    description     TEXT,
    aliases         TEXT[],                        -- 别名数组
    active_key_version INTEGER NOT NULL DEFAULT 1,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 初始化默认字段注册(L2/L3/L4)
INSERT INTO pii_field_registry (field_name, field_level, description, aliases, active_key_version)
VALUES
    ('full_name', 2, '姓名', ARRAY['name'], 1),
    ('email', 2, '邮箱', ARRAY[]::TEXT[], 1),
    ('phone', 2, '手机号', ARRAY[]::TEXT[], 1),
    ('id_card', 4, '身份证号', ARRAY['id_card_no','id_number'], 1),
    ('address', 3, '通讯地址', ARRAY[]::TEXT[], 1),
    ('bank_card', 3, '银行卡号', ARRAY['bank_account'], 1),
    ('resume_text', 3, '简历正文', ARRAY['cv_text'], 1),
    ('cv_text', 3, '简历正文 alias', ARRAY[]::TEXT[], 1),
    ('bio', 2, '个人简介', ARRAY[]::TEXT[], 1)
ON CONFLICT (field_name) DO NOTHING;

-- 候选人在网表标记
ALTER TABLE candidates
    ADD COLUMN IF NOT EXISTS pii_encryption_version INTEGER NOT NULL DEFAULT 1;

-- 用户表
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS pii_encryption_version INTEGER NOT NULL DEFAULT 1;

-- RLS:仅 DPO / 安全工程师可读写密钥相关表
ALTER TABLE pii_encryption_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE pii_key_rotation_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE pii_field_registry ENABLE ROW LEVEL SECURITY;

-- service role 可读写,普通用户无权限
DROP POLICY IF EXISTS pii_keys_service_only ON pii_encryption_keys;
CREATE POLICY pii_keys_service_only ON pii_encryption_keys
    FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);

DROP POLICY IF EXISTS pii_rotation_service_only ON pii_key_rotation_log;
CREATE POLICY pii_rotation_service_only ON pii_key_rotation_log
    FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);

DROP POLICY IF EXISTS pii_registry_service_only ON pii_field_registry;
CREATE POLICY pii_registry_service_only ON pii_field_registry
    FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);

-- 密钥轮转函数:为指定字段生成新密钥版本
CREATE OR REPLACE FUNCTION rotate_pii_key(
    p_field_name VARCHAR,
    p_new_version INTEGER,
    p_encrypted_key TEXT,
    p_rotated_by UUID,
    p_notes TEXT DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    new_id UUID;
    old_version INTEGER;
BEGIN
    -- 取当前 active 版本
    SELECT key_version INTO old_version
    FROM pii_encryption_keys
    WHERE field_name = p_field_name AND is_active = TRUE
    ORDER BY key_version DESC
    LIMIT 1;

    -- 旧版本标记为非 active
    UPDATE pii_encryption_keys
    SET is_active = FALSE
    WHERE field_name = p_field_name AND is_active = TRUE;

    -- 插入新版本
    INSERT INTO pii_encryption_keys (field_name, key_version, encrypted_key, rotated_by, notes)
    VALUES (p_field_name, p_new_version, p_encrypted_key, p_rotated_by, p_notes)
    RETURNING id INTO new_id;

    -- 写轮转日志
    INSERT INTO pii_key_rotation_log (field_name, old_version, new_version, rotated_by, notes)
    VALUES (p_field_name, old_version, p_new_version, p_rotated_by, p_notes);

    -- 更新注册表
    UPDATE pii_field_registry
    SET active_key_version = p_new_version, updated_at = NOW()
    WHERE field_name = p_field_name;

    RETURN new_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 注释
COMMENT ON TABLE pii_encryption_keys IS 'PII 字段级加密密钥表(多版本并存)';
COMMENT ON TABLE pii_key_rotation_log IS 'PII 密钥轮转审计日志';
COMMENT ON TABLE pii_field_registry IS 'PII 字段注册表 + active key 版本';
COMMENT ON FUNCTION rotate_pii_key IS '轮转指定字段的 PII 密钥';