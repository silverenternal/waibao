-- ============================================================
-- Migration 026: 视频面试 (T1305)
-- 表:
--   video_interviews       视频会议记录(每次安排一场会议)
--   video_webhooks         Zoom / 腾讯会议推送事件 (started / ended / recording_ready)
--   calendar_links         日历双向绑定(OAuth + 同步状态)
-- ============================================================

CREATE TABLE IF NOT EXISTS video_interviews (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id           UUID,                                -- HR 工单(可选, T1305 用)
    match_id            UUID,                                -- 候选人匹配(可选)
    candidate_id        UUID NOT NULL,
    employer_id         UUID NOT NULL,
    host_email          VARCHAR(255),
    topic               VARCHAR(255) NOT NULL DEFAULT '',
    provider            VARCHAR(32) NOT NULL DEFAULT 'mock',  -- zoom / tencent_meeting / mock
    meeting_id          VARCHAR(128) NOT NULL,               -- 供应商侧 id
    join_url            TEXT NOT NULL,
    host_url            TEXT,
    password            VARCHAR(64),
    start_time          TIMESTAMPTZ NOT NULL,
    duration_min        INT NOT NULL DEFAULT 30,
    status              VARCHAR(16) NOT NULL DEFAULT 'scheduled',  -- scheduled / started / ended / canceled / failed
    calendar_event_id   VARCHAR(128),
    calendar_synced_to  JSONB NOT NULL DEFAULT '[]'::JSONB,  -- ["google", "outlook"]
    recording_id        VARCHAR(128),
    recording_url       TEXT,
    transcript_url      TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_video_interviews_candidate ON video_interviews(candidate_id, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_video_interviews_employer  ON video_interviews(employer_id, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_video_interviews_ticket    ON video_interviews(ticket_id);
CREATE INDEX IF NOT EXISTS idx_video_interviews_meeting   ON video_interviews(meeting_id);


CREATE TABLE IF NOT EXISTS video_webhooks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider            VARCHAR(32) NOT NULL,               -- zoom / tencent_meeting
    event_type          VARCHAR(64) NOT NULL,               -- meeting.started / ended / recording_ready
    meeting_id          VARCHAR(128) NOT NULL,
    video_interview_id  UUID REFERENCES video_interviews(id) ON DELETE SET NULL,
    payload             JSONB NOT NULL DEFAULT '{}'::JSONB,
    processed           BOOLEAN NOT NULL DEFAULT FALSE,
    processed_at        TIMESTAMPTZ,
    received_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_video_webhooks_unprocessed ON video_webhooks(processed, received_at) WHERE processed = FALSE;
CREATE INDEX IF NOT EXISTS idx_video_webhooks_meeting    ON video_webhooks(meeting_id);


CREATE TABLE IF NOT EXISTS calendar_links (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    employer_id         UUID,
    provider            VARCHAR(16) NOT NULL,                -- google / outlook
    account_email       VARCHAR(255),
    access_token        TEXT NOT NULL,
    refresh_token       TEXT,
    expires_at          TIMESTAMPTZ,
    scope               TEXT,
    last_sync_at        TIMESTAMPTZ,
    last_error          TEXT,
    enabled             BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_calendar_links_user_provider
    ON calendar_links(user_id, provider);
CREATE INDEX IF NOT EXISTS idx_calendar_links_employer ON calendar_links(employer_id);
