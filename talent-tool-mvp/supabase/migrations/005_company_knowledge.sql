-- ============================================================
-- Migration 005: 企业知识库 (愿景/规划/战略/战术/制度)
-- ============================================================

-- 企业愿景/战略层级
CREATE TABLE IF NOT EXISTS company_strategy (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id UUID NOT NULL,
    level           TEXT NOT NULL CHECK (level IN ('vision', 'planning', 'strategy', 'tactic')),
    horizon         TEXT,                            -- 3y / 1y / 6m / 1m
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    owner_role      TEXT NOT NULL,                   -- boss / hr / dept_head
    owner_user_id   UUID,
    parent_id       UUID REFERENCES company_strategy(id) ON DELETE CASCADE,
    status          TEXT DEFAULT 'active' CHECK (status IN ('draft', 'active', 'archived')),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_strategy_org_level
    ON company_strategy (organisation_id, level);

CREATE INDEX IF NOT EXISTS idx_company_strategy_parent
    ON company_strategy (parent_id);

-- 资质文件 (营业执照/法人证件/行业资质)
CREATE TABLE IF NOT EXISTS company_credentials (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id UUID NOT NULL,
    credential_type TEXT NOT NULL CHECK (credential_type IN (
        'business_license', 'legal_id', 'industry_cert', 'tax_cert',
        'bank_account', 'org_chart', 'patent', 'other'
    )),
    file_url        TEXT NOT NULL,
    file_name       TEXT,
    verified        BOOLEAN DEFAULT FALSE,
    verified_at     TIMESTAMPTZ,
    verified_by     TEXT,                            -- system / manual / external
    ocr_data        JSONB DEFAULT '{}'::jsonb,       -- OCR 提取的字段
    external_lookup JSONB DEFAULT '{}'::jsonb,       -- 工商系统查询结果
    trust_score     NUMERIC(3,2),                    -- 0.0 ~ 1.0
    expires_at      TIMESTAMPTZ,
    notes           TEXT,
    uploaded_by     UUID,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_credentials_org
    ON company_credentials (organisation_id, credential_type);

-- 制度库 (考勤/请假/报销/晋升/薪酬)
CREATE TABLE IF NOT EXISTS company_policies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id UUID NOT NULL,
    category        TEXT NOT NULL CHECK (category IN (
        'attendance', 'leave', 'expense', 'promotion', 'salary',
        'benefits', 'conduct', 'safety', 'remote_work', 'other'
    )),
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    effective_from  DATE,
    embedding       VECTOR(1536),                    -- pgvector 用于 RAG 检索
    uploaded_by     UUID,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_policies_org_cat
    ON company_policies (organisation_id, category);

CREATE INDEX IF NOT EXISTS idx_company_policies_embedding
    ON company_policies USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- 启用 RLS
ALTER TABLE company_strategy ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_policies ENABLE ROW LEVEL SECURITY;

-- 同组织成员可见(简化策略:所有人同组织可见)
CREATE POLICY "Org members access strategy" ON company_strategy
    FOR ALL USING (true) WITH CHECK (true);   -- 由应用层做更细粒度控制
CREATE POLICY "Org members access credentials" ON company_credentials
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Org members access policies" ON company_policies
    FOR ALL USING (true) WITH CHECK (true);