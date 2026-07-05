-- ============================================================
-- Migration 008: PII 加密 (T403)
-- 字段级加密, 配合 backend/services/crypto.py
-- ============================================================

-- 创建 pgcrypto 扩展 (AES-GCM)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 求职者邮箱/手机/身份证加密视图
CREATE OR REPLACE VIEW candidates_pii_safe AS
SELECT
    id,
    first_name,
    last_name,
    -- 用 pgp_sym_encrypt 加密敏感字段; 解密需要密钥
    encode(encrypt(email::bytea, current_setting('app.pii_key'), 'aes'), 'base64') AS email_encrypted,
    encode(encrypt(phone::bytea, current_setting('app.pii_key'), 'aes'), 'base64') AS phone_encrypted,
    location,
    skills,
    experience,
    seniority,
    created_at
FROM candidates;

-- 用户"被遗忘权"函数 (GDPR / 个保法 合规)
CREATE OR REPLACE FUNCTION forget_user(target_user_id UUID)
RETURNS void AS $$
BEGIN
    -- 删除日记
    DELETE FROM daily_journals WHERE user_id = target_user_id;
    -- 删除情绪时间线
    DELETE FROM emotion_timeline WHERE user_id = target_user_id;
    -- 删除对话
    DELETE FROM conversations WHERE user_id = target_user_id;
    -- 删除记忆
    DELETE FROM agent_memory WHERE user_id = target_user_id;
    -- 匿名化候选人 (保留统计,但抹去 PII)
    UPDATE candidates
    SET first_name = 'REDACTED',
        last_name = 'REDACTED',
        email = NULL,
        phone = NULL,
        cv_text = '[REDACTED]'
    WHERE created_by = target_user_id;
    -- 删除职业规划
    DELETE FROM career_plans WHERE user_id = target_user_id;
    -- 删除澄清
    DELETE FROM candidate_clarifications WHERE user_id = target_user_id;
    -- 标记用户为已删除
    UPDATE users SET deleted_at = NOW(), is_active = FALSE WHERE id = target_user_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 数据导出函数 (GDPR)
CREATE OR REPLACE FUNCTION export_user_data(target_user_id UUID)
RETURNS JSONB AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'profile', (SELECT to_jsonb(c) FROM candidates c WHERE c.created_by = target_user_id),
        'journals', (SELECT jsonb_agg(to_jsonb(j)) FROM daily_journals j WHERE j.user_id = target_user_id),
        'emotions', (SELECT jsonb_agg(to_jsonb(e)) FROM emotion_timeline e WHERE e.user_id = target_user_id),
        'plans', (SELECT jsonb_agg(to_jsonb(p)) FROM career_plans p WHERE p.user_id = target_user_id),
        'clarifications', (SELECT jsonb_agg(to_jsonb(c)) FROM candidate_clarifications c WHERE c.user_id = target_user_id)
    ) INTO result;
    RETURN result;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;