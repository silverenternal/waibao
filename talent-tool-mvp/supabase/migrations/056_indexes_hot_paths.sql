-- ============================================================================
-- 056_indexes_hot_paths.sql
-- T5011 (part 2) — hot-path composite / partial / INCLUDE indexes.
--
-- Each index targets a measured query shape from the backend (see the
-- AUDIT_DATABASE.md hot-path list).  They are created CONCURRENTLY so the
-- migration is safe to run on a live primary without blocking writes.
--
-- NOTE on CREATE INDEX CONCURRENTLY:
--   * cannot run inside a transaction block → this file is NOT wrapped in
--     BEGIN/COMMIT;
--   * each statement is independently idempotent via ``IF NOT EXISTS``.
--
-- Indexes (6 hot paths):
--   1. candidates  — tenant-scoped semantic search (INCLUDE id for covering)
--   2. matches     — tenant + active status, covering score (INCLUDE)
--   3. tickets     — tenant + open statuses (PARTIAL, SLA hot path)
--   4. emotion_timeline — tenant + attention seekers (PARTIAL)
--   5. daily_journals — tenant + recent (composite)
--   6. candidates  — tenant + dedup lookup (composite, dedup worker)
--   7. matches     — tenant + role drilldown (composite)
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. candidates — tenant-scoped vector candidates.
--    The semantic-search RPC filters ``WHERE tenant_id = $1 ORDER BY embedding
--    <=> $2 LIMIT k``.  INCLUDE(id) makes the index covering for the common
--    "fetch ids then hydrate" path.
-- ---------------------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_candidates_tenant_embedding
    ON public.candidates (tenant_id)
    INCLUDE (id)
    WHERE embedding IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 2. matches — tenant + "active" statuses, covering the score column.
--    Hot path: recruiter "shortlist for role X" lists non-dismissed matches
--    ordered by score.  INCLUDE(overall_score, role_id) turns it into an
--    index-only scan.
-- ---------------------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_matches_tenant_active_score
    ON public.matches (tenant_id, candidate_id)
    INCLUDE (overall_score, role_id)
    WHERE status <> 'dismissed';

-- ---------------------------------------------------------------------------
-- 3. tickets — SLA dashboard: open tickets per tenant ordered by due date.
--    PARTIAL index so only the working set (open / in_progress / awaiting)
--    is materialised.
-- ---------------------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tickets_tenant_open_sla
    ON public.tickets (tenant_id, priority, sla_due_at)
    WHERE status IN ('open', 'in_progress', 'awaiting_user');

-- ---------------------------------------------------------------------------
-- 4. emotion_timeline — proactive-care worker scans for attention seekers.
--    PARTIAL: only the small slice of rows that need a human.
-- ---------------------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emotion_timeline_tenant_attention
    ON public.emotion_timeline (tenant_id, user_id, recorded_at DESC)
    WHERE needs_attention = TRUE;

-- ---------------------------------------------------------------------------
-- 5. daily_journals — jobseeker "recent entries" feed per tenant+user.
--    Exposed as journal_entries in the cloud schema.
-- ---------------------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_journal_entries_tenant_user_recent
    ON public.journal_entries (tenant_id, user_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- 6. candidates — dedup worker: find same dedup_group within a tenant.
--    Hot path: nightly dedup job groups duplicates per tenant.
-- ---------------------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_candidates_tenant_dedup
    ON public.candidates (tenant_id, dedup_group)
    WHERE dedup_group IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 7. matches — recruiter drilldown: all matches for a role within tenant.
-- ---------------------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_matches_tenant_role
    ON public.matches (tenant_id, role_id, status);

-- ---------------------------------------------------------------------------
-- 8. bonus covering index — tickets comment lookup (avoid heap fetch).
-- ---------------------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tickets_tenant_id_include
    ON public.tickets (tenant_id)
    INCLUDE (id, status, priority, updated_at);

-- ---------------------------------------------------------------------------
-- 9. ANALYZE so the planner picks up the new indexes immediately.
--    (CONCURRENTLY-built indexes are visible but stats may be stale.)
-- ---------------------------------------------------------------------------
ANALYZE public.candidates;
ANALYZE public.matches;
ANALYZE public.tickets;
ANALYZE public.emotion_timeline;
ANALYZE public.journal_entries;
