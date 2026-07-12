-- ============================================================
-- Migration 027: 测评 (T1306) — 北森 / HackerRank / 光辉国际 等
--   assessment_invitations  每次测评邀请
--   candidates 新增字段: assessment_score / assessment_confidence
-- ============================================================

CREATE TABLE IF NOT EXISTS assessment_invitations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invitation_id       VARCHAR(128) NOT NULL,            -- 供应商侧 id
    candidate_id        UUID NOT NULL,
    assessment_id       VARCHAR(128) NOT NULL,
    provider            VARCHAR(32) NOT NULL DEFAULT 'mock',
    status              VARCHAR(16) NOT NULL DEFAULT 'pending',  -- pending / started / submitted / scored / expired / canceled
    invite_url          TEXT,
    expires_at          TIMESTAMPTZ,
    job_id              UUID,
    metadata            JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_assess_inv_candidate
    ON assessment_invitations(candidate_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_assess_inv_job
    ON assessment_invitations(job_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_assess_inv_invitation
    ON assessment_invitations(invitation_id);


-- 在 candidates 表增加 assessment 字段 (幂等)
ALTER TABLE candidates
    ADD COLUMN IF NOT EXISTS assessment_score          DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS assessment_confidence     VARCHAR(16),
    ADD COLUMN IF NOT EXISTS assessment_updated_at     TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_candidates_assessment
    ON candidates(assessment_score DESC)
    WHERE assessment_score IS NOT NULL;
