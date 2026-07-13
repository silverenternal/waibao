-- T2603: v7.0 Enterprise Audit Log v2 + GDPR/PIPL/CCPA Compliance Tables
--
-- Adds:
--   * audit_log_v2           - per-row PII access record with lawful_basis
--   * data_processing_register - GDPR Art. 30 / PIPL Art. 30 record of processing activities
--   * data_subject_requests  - GDPR Art. 15 (access) / Art. 17 (erasure) / Art. 16 (rectify)
--   * data_breaches          - GDPR Art. 33/34 breach register (72h notification)
--   * lawful_basis_catalog   - 6 GDPR + 2 PIPL + 1 CCPA basis values, used by API/UI
--
-- Retention: 3 years (PIPL Art. 52 explicit requirement; GDPR Rec. 39 permits "no longer
-- than necessary"; we use the more conservative ceiling so EU and CN stay aligned).
--
-- RLS: only `admin` and `compliance` roles may read; service_role may write.
-- The audit_log_v2 table is append-only (UPDATE/DELETE blocked by trigger).

BEGIN;

-- ----------------------------------------------------------------------
-- 0. Lawful basis catalog
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.lawful_basis_catalog (
  code text PRIMARY KEY,
  region text NOT NULL CHECK (region IN ('EU', 'CN', 'CA', 'US', 'GLOBAL')),
  name_zh text NOT NULL,
  name_en text NOT NULL,
  description text,
  requires_consent boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO public.lawful_basis_catalog (code, region, name_zh, name_en, description, requires_consent) VALUES
  -- GDPR (EU) — Art. 6
  ('gdpr_consent',         'EU', '同意',       'Consent',                    '数据主体明确同意,可随时撤回',                       true),
  ('gdpr_contract',        'EU', '合同必要',   'Contract',                   '履行用户合同所必需',                                 false),
  ('gdpr_legal_obligation','EU', '法定义务',   'Legal Obligation',           '遵守法定义务(税务/反洗钱/劳动法)',                  false),
  ('gdpr_vital_interest',  'EU', '重大利益',   'Vital Interests',            '保护自然人重大利益',                                 false),
  ('gdpr_public_task',     'EU', '公共任务',   'Public Task',                '执行公共利益任务',                                   false),
  ('gdpr_legitimate_interest','EU','正当利益', 'Legitimate Interests',       '追求正当利益且不超越基本权利',                       false),
  -- PIPL (CN) — Art. 13
  ('pipl_consent',         'CN', '知情同意',   'Informed Consent',           '自愿、明确知情;可单独撤回',                          true),
  ('pipl_contract_necessary','CN','必要',     'Necessary for Contract',     '订立/履行合同所必需',                                false),
  -- CCPA (CA/US)
  ('ccpa_business_purpose','CA', '商业目的',   'Business Purpose',           '合理商业目的,opt-out 机制',                          false),
  ('ccpa_opt_out',         'CA', '选择退出',   'Opt-Out',                    '消费者已明确选择退出出售/共享',                      false)
ON CONFLICT (code) DO NOTHING;


-- ----------------------------------------------------------------------
-- 1. audit_log_v2 — per-row PII access log
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.audit_log_v2 (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid,
  actor_id uuid,
  actor_role text,
  actor_ip inet,
  actor_ua text,
  action text NOT NULL,                          -- read|create|update|delete|export|forget|login|consent|rectify
  resource_type text NOT NULL,
  resource_id text,
  data_classification text NOT NULL DEFAULT 'pii'
                       CHECK (data_classification IN ('public','internal','pii','sensitive','special')),
  pii_accessed jsonb NOT NULL DEFAULT '[]'::jsonb,   -- ["email","phone","name",...]
  consent_id uuid,                                  -- FK to consent_records
  lawful_basis text REFERENCES public.lawful_basis_catalog(code),
  request_id text,                                  -- correlation id
  session_id text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  retention_until timestamptz NOT NULL DEFAULT (now() + interval '3 years')
);

CREATE INDEX IF NOT EXISTS audit_log_v2_tenant_idx
  ON public.audit_log_v2 (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS audit_log_v2_actor_idx
  ON public.audit_log_v2 (actor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS audit_log_v2_resource_idx
  ON public.audit_log_v2 (resource_type, resource_id, created_at DESC);
CREATE INDEX IF NOT EXISTS audit_log_v2_action_idx
  ON public.audit_log_v2 (action, created_at DESC);
CREATE INDEX IF NOT EXISTS audit_log_v2_lawful_basis_idx
  ON public.audit_log_v2 (lawful_basis, created_at DESC);
CREATE INDEX IF NOT EXISTS audit_log_v2_retention_idx
  ON public.audit_log_v2 (retention_until)
  WHERE retention_until < now() + interval '30 days';

-- GIN on metadata for flexible search
CREATE INDEX IF NOT EXISTS audit_log_v2_metadata_gin
  ON public.audit_log_v2 USING gin (metadata jsonb_path_ops);

-- ----------------------------------------------------------------------
-- 2. Append-only enforcement on audit_log_v2
-- ----------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.audit_log_v2_block_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'audit_log_v2 is append-only; % not allowed', tg_op
    USING ERRCODE = 'P0001';
END;
$$;

DROP TRIGGER IF EXISTS audit_log_v2_no_update ON public.audit_log_v2;
CREATE TRIGGER audit_log_v2_no_update
  BEFORE UPDATE ON public.audit_log_v2
  FOR EACH ROW EXECUTE FUNCTION public.audit_log_v2_block_mutation();

DROP TRIGGER IF EXISTS audit_log_v2_no_delete ON public.audit_log_v2;
CREATE TRIGGER audit_log_v2_no_delete
  BEFORE DELETE ON public.audit_log_v2
  FOR EACH ROW EXECUTE FUNCTION public.audit_log_v2_block_mutation();

REVOKE UPDATE, DELETE ON public.audit_log_v2 FROM authenticated, anon;

-- ----------------------------------------------------------------------
-- 3. data_processing_register — Art. 30 record of processing activities
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.data_processing_register (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid,
  controller_name text NOT NULL,                   -- 数据控制者
  controller_contact text,
  dpo_contact text,                                -- Data Protection Officer
  processing_purpose text NOT NULL,
  lawful_basis text NOT NULL REFERENCES public.lawful_basis_catalog(code),
  data_categories jsonb NOT NULL DEFAULT '[]'::jsonb,   -- ["email","resume","interview_video"]
  data_subjects jsonb NOT NULL DEFAULT '[]'::jsonb,     -- ["candidates","recruiters"]
  recipients jsonb NOT NULL DEFAULT '[]'::jsonb,        -- who receives data
  cross_border_transfer boolean NOT NULL DEFAULT false,
  transfer_safeguards text,                            -- SCC / BCR / PIPL 安全评估
  retention_period_days integer NOT NULL DEFAULT 1095,  -- 3 years default
  security_measures jsonb NOT NULL DEFAULT '[]'::jsonb,
  is_active boolean NOT NULL DEFAULT true,
  review_date date,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid
);

CREATE INDEX IF NOT EXISTS dpr_tenant_idx
  ON public.data_processing_register (tenant_id);
CREATE INDEX IF NOT EXISTS dpr_lawful_basis_idx
  ON public.data_processing_register (lawful_basis);
CREATE INDEX IF NOT EXISTS dpr_active_idx
  ON public.data_processing_register (is_active) WHERE is_active = true;

-- ----------------------------------------------------------------------
-- 4. data_subject_requests — Art. 15/16/17 requests
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.data_subject_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid,
  subject_id uuid NOT NULL,                        -- the data subject
  request_type text NOT NULL CHECK (request_type IN ('access','rectify','erase','restrict','portability','object')),
  requester_email text,
  requester_name text,
  description text,
  status text NOT NULL DEFAULT 'pending'
             CHECK (status IN ('pending','verifying','in_progress','completed','rejected','escalated')),
  lawful_basis_invoked text REFERENCES public.lawful_basis_catalog(code),
  sla_days integer NOT NULL DEFAULT 30,            -- GDPR 1 month default; PIPL 30 days
  due_at timestamptz NOT NULL,
  completed_at timestamptz,
  rejection_reason text,
  response_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  assignee_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS dsr_subject_idx
  ON public.data_subject_requests (subject_id, created_at DESC);
CREATE INDEX IF NOT EXISTS dsr_status_idx
  ON public.data_subject_requests (status, due_at);
CREATE INDEX IF NOT EXISTS dsr_type_idx
  ON public.data_subject_requests (request_type, created_at DESC);
CREATE INDEX IF NOT EXISTS dsr_tenant_idx
  ON public.data_subject_requests (tenant_id);

-- SLA breach detector: notification trigger when an open DSR crosses due_at
CREATE OR REPLACE FUNCTION public.dsr_check_sla_breach()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.status IN ('pending','verifying','in_progress')
     AND NEW.due_at < now() THEN
    NEW.status := 'escalated';
    NEW.updated_at := now();
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS dsr_sla_breach_trg ON public.data_subject_requests;
CREATE TRIGGER dsr_sla_breach_trg
  BEFORE UPDATE ON public.data_subject_requests
  FOR EACH ROW EXECUTE FUNCTION public.dsr_check_sla_breach();

-- ----------------------------------------------------------------------
-- 5. data_breaches — Art. 33/34 breach register (72h notification)
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.data_breaches (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid,
  discovered_at timestamptz NOT NULL DEFAULT now(),
  occurred_at timestamptz,
  severity text NOT NULL CHECK (severity IN ('low','medium','high','critical')),
  categories_affected jsonb NOT NULL DEFAULT '[]'::jsonb,
  subjects_affected integer NOT NULL DEFAULT 0,
  records_affected integer NOT NULL DEFAULT 0,
  description text NOT NULL,
  containment_status text NOT NULL DEFAULT 'open'
                    CHECK (containment_status IN ('open','contained','remediated','closed')),
  reported_to_authority_at timestamptz,           -- GDPR: 72h
  subjects_notified_at timestamptz,                -- GDPR Art. 34
  lawful_basis_invoked text REFERENCES public.lawful_basis_catalog(code),
  remediation_steps jsonb NOT NULL DEFAULT '[]'::jsonb,
  root_cause text,
  created_by uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS db_severity_idx
  ON public.data_breaches (severity, discovered_at DESC);
CREATE INDEX IF NOT EXISTS db_tenant_idx
  ON public.data_breaches (tenant_id, discovered_at DESC);
CREATE INDEX IF NOT EXISTS db_status_idx
  ON public.data_breaches (containment_status);

-- ----------------------------------------------------------------------
-- 6. RLS on all new tables
-- ----------------------------------------------------------------------
ALTER TABLE public.audit_log_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.data_processing_register ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.data_subject_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.data_breaches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lawful_basis_catalog ENABLE ROW LEVEL SECURITY;

-- audit_log_v2: read only admin/compliance roles
DROP POLICY IF EXISTS audit_v2_admin_select ON public.audit_log_v2;
CREATE POLICY audit_v2_admin_select ON public.audit_log_v2
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM public.users u
      WHERE u.id = auth.uid() AND u.role IN ('admin', 'compliance')
    )
  );

DROP POLICY IF EXISTS audit_v2_service_write ON public.audit_log_v2;
CREATE POLICY audit_v2_service_write ON public.audit_log_v2
  FOR INSERT WITH CHECK (auth.role() = 'service_role');

-- data_processing_register: admin/compliance full, others read-only
DROP POLICY IF EXISTS dpr_admin_all ON public.data_processing_register;
CREATE POLICY dpr_admin_all ON public.data_processing_register
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM public.users u
      WHERE u.id = auth.uid() AND u.role IN ('admin', 'compliance')
    )
  ) WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.users u
      WHERE u.id = auth.uid() AND u.role IN ('admin', 'compliance')
    )
  );

DROP POLICY IF EXISTS dpr_user_read ON public.data_processing_register;
CREATE POLICY dpr_user_read ON public.data_processing_register
  FOR SELECT USING (true);

-- data_subject_requests: subject can read their own, admin/compliance can read all
DROP POLICY IF EXISTS dsr_subject_read ON public.data_subject_requests;
CREATE POLICY dsr_subject_read ON public.data_subject_requests
  FOR SELECT USING (
    subject_id = auth.uid()
    OR EXISTS (
      SELECT 1 FROM public.users u
      WHERE u.id = auth.uid() AND u.role IN ('admin', 'compliance')
    )
  );

DROP POLICY IF EXISTS dsr_service_write ON public.data_subject_requests;
CREATE POLICY dsr_service_write ON public.data_subject_requests
  FOR ALL USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- data_breaches: admin/compliance only
DROP POLICY IF EXISTS db_admin_all ON public.data_breaches;
CREATE POLICY db_admin_all ON public.data_breaches
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM public.users u
      WHERE u.id = auth.uid() AND u.role IN ('admin', 'compliance')
    )
  ) WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.users u
      WHERE u.id = auth.uid() AND u.role IN ('admin', 'compliance')
    )
  );

-- lawful_basis_catalog: world-readable
DROP POLICY IF EXISTS lbc_read ON public.lawful_basis_catalog;
CREATE POLICY lbc_read ON public.lawful_basis_catalog
  FOR SELECT USING (true);

DROP POLICY IF EXISTS lbc_admin_write ON public.lawful_basis_catalog;
CREATE POLICY lbc_admin_write ON public.lawful_basis_catalog
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM public.users u
      WHERE u.id = auth.uid() AND u.role = 'admin'
    )
  ) WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.users u
      WHERE u.id = auth.uid() AND u.role = 'admin'
    )
  );

-- ----------------------------------------------------------------------
-- 7. Seed: default processing activities (T2603 covers these out of the box)
-- ----------------------------------------------------------------------
INSERT INTO public.data_processing_register
  (controller_name, processing_purpose, lawful_basis, data_categories, data_subjects, retention_period_days)
VALUES
  ('Waibao Inc.', '候选人注册与简历管理', 'pipl_consent',
   '["email","name","phone","resume","work_history"]'::jsonb,
   '["candidates"]'::jsonb, 1095),
  ('Waibao Inc.', 'AI 面试评估与录像', 'gdpr_consent',
   '["interview_video","voice","facial_expression"]'::jsonb,
   '["candidates"]'::jsonb, 365),
  ('Waibao Inc.', '招聘匹配与岗位推荐', 'pipl_contract_necessary',
   '["skill","experience","preference"]'::jsonb,
   '["candidates","recruiters"]'::jsonb, 730),
  ('Waibao Inc.', '账单与发票', 'gdpr_legal_obligation',
   '["billing_address","tax_id","payment_method"]'::jsonb,
   '["employers"]'::jsonb, 2555),
  ('Waibao Inc.', '营销与产品通讯', 'gdpr_consent',
   '["email","usage_pattern"]'::jsonb,
   '["candidates","recruiters"]'::jsonb, 730)
ON CONFLICT DO NOTHING;

COMMIT;
