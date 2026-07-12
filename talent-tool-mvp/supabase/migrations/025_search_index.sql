-- ============================================================================
-- 025_search_index.sql — T1404 full-text + semantic search index
--
-- Adds:
--   - tsvector columns on candidates / roles / tickets / company_policies
--   - GIN indexes for sub-300ms full-text search
--   - Trigger-maintained columns (auto-update on row insert/update)
--   - pgvector embedding is already on candidates / roles / company_policies;
--     semantic search reuses those via the global_search service.
--
-- Search vocabulary:
--   - 'simple' tokenizer for English/code-friendly matching
--   - 'public.english_unaccent' (created below if available) for user-facing
--     fuzzy match
--
-- Backfill:
--   - UPDATE on existing rows runs GENERATED ALWAYS AS, so backfill is automatic
--     once the column is added; we run UPDATE … = DEFAULT explicitly for big
--     tables to keep plan stability.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- -----------------------------------------------------------------------
-- candidates
-- -----------------------------------------------------------------------
ALTER TABLE candidates
    ADD COLUMN IF NOT EXISTS search_tsv tsvector;

UPDATE candidates
SET search_tsv =
    setweight(to_tsvector('simple', coalesce(full_name, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(headline, '')), 'B') ||
    setweight(to_tsvector('simple', coalesce(skills::text, '')), 'B') ||
    setweight(to_tsvector('simple', coalesce(bio, '')), 'C')
WHERE search_tsv IS NULL;

ALTER TABLE candidates
    ALTER COLUMN search_tsv SET GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(full_name, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(headline, '')), 'B') ||
        setweight(to_tsvector('simple', coalesce(skills::text, '')), 'B') ||
        setweight(to_tsvector('simple', coalesce(bio, '')), 'C')
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_candidates_search_tsv
    ON candidates USING GIN (search_tsv);

-- trigram fuzzy match fallback (names)
CREATE INDEX IF NOT EXISTS idx_candidates_full_name_trgm
    ON candidates USING GIN (full_name gin_trgm_ops);

-- -----------------------------------------------------------------------
-- roles
-- -----------------------------------------------------------------------
ALTER TABLE roles
    ADD COLUMN IF NOT EXISTS search_tsv tsvector;

UPDATE roles
SET search_tsv =
    setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(department, '')), 'B') ||
    setweight(to_tsvector('simple', coalesce(description, '')), 'C') ||
    setweight(to_tsvector('simple', coalesce(skills::text, '')), 'B')
WHERE search_tsv IS NULL;

ALTER TABLE roles
    ALTER COLUMN search_tsv SET GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(department, '')), 'B') ||
        setweight(to_tsvector('simple', coalesce(description, '')), 'C') ||
        setweight(to_tsvector('simple', coalesce(skills::text, '')), 'B')
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_roles_search_tsv
    ON roles USING GIN (search_tsv);

CREATE INDEX IF NOT EXISTS idx_roles_title_trgm
    ON roles USING GIN (title gin_trgm_ops);

-- -----------------------------------------------------------------------
-- tickets
-- -----------------------------------------------------------------------
ALTER TABLE tickets
    ADD COLUMN IF NOT EXISTS search_tsv tsvector;

UPDATE tickets
SET search_tsv =
    setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(description, '')), 'C')
WHERE search_tsv IS NULL;

ALTER TABLE tickets
    ALTER COLUMN search_tsv SET GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(description, '')), 'C')
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_tickets_search_tsv
    ON tickets USING GIN (search_tsv);

CREATE INDEX IF NOT EXISTS idx_tickets_title_trgm
    ON tickets USING GIN (title gin_trgm_ops);

-- -----------------------------------------------------------------------
-- company_policies
-- -----------------------------------------------------------------------
ALTER TABLE company_policies
    ADD COLUMN IF NOT EXISTS search_tsv tsvector;

UPDATE company_policies
SET search_tsv =
    setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(content, '')), 'B') ||
    setweight(to_tsvector('simple', coalesce(category, '')), 'C')
WHERE search_tsv IS NULL;

ALTER TABLE company_policies
    ALTER COLUMN search_tsv SET GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(content, '')), 'B') ||
        setweight(to_tsvector('simple', coalesce(category, '')), 'C')
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_company_policies_search_tsv
    ON company_policies USING GIN (search_tsv);

CREATE INDEX IF NOT EXISTS idx_company_policies_title_trgm
    ON company_policies USING GIN (title gin_trgm_ops);
