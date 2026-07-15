-- v11.0 T6110 — Mandatory human-escalation risk alerts.
--
-- When the governance layer (agents/governance.py EscalationRules) detects a
-- mandatory-escalation topic (self-harm / labour dispute), the escalation
-- service persists ONE redacted row here.  Per 甲方要求:
--   * admins/HR see only risk_level + reason (+ matched-keyword category hint
--     + ticket id) — NEVER the user's raw private conversation;
--   * the original chat rows stay behind their own user-scoped RLS, so even a
--     platform admin cannot read them.
--
-- This table therefore intentionally has NO verbatim-text column.  The
-- `message` column holds the warm popup copy shown to the *user*, not their
-- words.

BEGIN;

CREATE TABLE IF NOT EXISTS public.risk_alerts (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           TEXT NOT NULL,
    organisation_id   TEXT,
    tenant_id         UUID,                          -- v8.0 multi-tenant column

    rule              TEXT NOT NULL CHECK (rule IN ('self_harm', 'labour_dispute')),
    risk_level        TEXT NOT NULL CHECK (risk_level IN ('critical', 'high')),

    -- PII-free, human-readable reason; never the verbatim conversation.
    reason            TEXT NOT NULL DEFAULT '',
    -- Category hint only (e.g. ['自杀','想死']) — not the user's full sentence.
    matched_keywords  JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Warm popup copy shown to the user (hotline etc.).
    message           TEXT NOT NULL DEFAULT '',

    ticket_id         TEXT,                          -- optional HR/legal ticket
    notified          BOOLEAN NOT NULL DEFAULT FALSE,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_risk_alerts_user        ON public.risk_alerts (user_id);
CREATE INDEX IF NOT EXISTS idx_risk_alerts_risk_level  ON public.risk_alerts (risk_level);
CREATE INDEX IF NOT EXISTS idx_risk_alerts_created_at  ON public.risk_alerts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_alerts_org         ON public.risk_alerts (organisation_id) WHERE organisation_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- RLS: only the subject user OR hr/admin of the same org/tenant can read the
-- (already redacted) summary.  Nobody reads raw chat through this table.
-- ---------------------------------------------------------------------------
ALTER TABLE public.risk_alerts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "risk_alerts_self_or_hr_admin_read" ON public.risk_alerts;

CREATE POLICY "risk_alerts_self_or_hr_admin_read" ON public.risk_alerts
    FOR SELECT USING (
        -- subject sees their own (redacted) alerts
        auth.uid()::text = user_id
        OR EXISTS (
            SELECT 1 FROM public.org_members om
            WHERE om.user_id = auth.uid()::text
              AND om.role IN ('hr', 'admin', 'talent_partner')
        )
    );

-- Service-role (backend) performs inserts via the service key; no INSERT
-- policy is needed for end users.
DROP POLICY IF EXISTS "risk_alerts_service_insert" ON public.risk_alerts;
CREATE POLICY "risk_alerts_service_insert" ON public.risk_alerts
    FOR INSERT WITH CHECK (TRUE);

COMMIT;
