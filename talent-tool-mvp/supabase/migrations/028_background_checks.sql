-- ============================================================
-- Migration 028: 背景调查 (T1307) — Checkr / iCIMS / HireRight
-- ============================================================

CREATE TABLE IF NOT EXISTS background_checks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    check_id            VARCHAR(128) NOT NULL,           -- 供应商侧 id
    candidate_id        UUID NOT NULL,
    provider            VARCHAR(32) NOT NULL DEFAULT 'mock',
    status              VARCHAR(16) NOT NULL DEFAULT 'pending',
    -- pending / in_progress / clear / consider / suspended
    check_types         JSONB NOT NULL DEFAULT '[]'::JSONB,
    report_url          TEXT,
    offer_id            UUID,                           -- 关联 offer
    job_id              UUID,
    findings            JSONB NOT NULL DEFAULT '[]'::JSONB,
    metadata            JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_bg_check_candidate ON background_checks(candidate_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_bg_check_offer     ON background_checks(offer_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_bg_check_id     ON background_checks(check_id);
CREATE INDEX IF NOT EXISTS idx_bg_check_status    ON background_checks(status);
