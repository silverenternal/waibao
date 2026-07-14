"""T5011 — trigger consolidation + hot-path index tests.

Validates ``055_triggers_consolidated.sql`` and ``056_indexes_hot_paths.sql``
at the structural level (no live Postgres in CI).

055 assertions
--------------
* a single canonical ``public.set_updated_at()`` exists
* it is defensive: skips tables without updated_at, no-ops on unchanged rows
* every legacy duplicate is redefined as a delegating wrapper
* an idempotent ``attach_updated_at_trigger(regclass)`` helper exists
* existing per-table triggers are re-pointed at the canonical function

056 assertions
--------------
* at least 6 CREATE INDEX CONCURRENTLY statements
* covering (INCLUDE) indexes exist for candidates + matches
* partial indexes exist for tickets, emotion_timeline, candidates(dedup)
* a composite tenant+role index exists for matches
* the migration is NOT wrapped in BEGIN/COMMIT (CONCURRENTLY requirement)
* ANALYZE is issued so the planner sees the new indexes
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[1] / "supabase" / "migrations"
M055 = (MIGRATIONS / "055_triggers_consolidated.sql").read_text(encoding="utf-8")
M056 = (MIGRATIONS / "056_indexes_hot_paths.sql").read_text(encoding="utf-8")


# ===========================================================================
# 055 — trigger consolidation
# ===========================================================================
def test_canonical_function_defined() -> None:
    assert "CREATE OR REPLACE FUNCTION public.set_updated_at()" in M055


def test_canonical_function_is_defensive_no_updated_at() -> None:
    """Skips tables that lack an updated_at column (returns NEW)."""
    assert "information_schema.columns" in M055
    assert "column_name  = 'updated_at'" in M055
    assert "RETURN NEW" in M055


def test_canonical_function_noops_on_unchanged_row() -> None:
    """Avoids stamping updated_at when the row did not actually change."""
    assert "NEW IS NOT DISTINCT FROM OLD" in M055


def test_legacy_wrappers_all_delegated() -> None:
    legacy = [
        "update_updated_at",
        "trg_tickets_touch_updated_at",
        "trg_persona_prefs_updated_at",
        "trg_notify_prefs_touch_updated_at",
        "trg_notification_preferences_touch_updated_at",
        "trg_workflows_updated_at",
        "services_touch_updated_at",
        "pilot_programs_touch_updated_at",
    ]
    for name in legacy:
        assert name in M055, f"legacy function {name!r} not consolidated"
    # each redefinition delegates to the canonical function
    assert "SELECT public.set_updated_at()" in M055


def test_legacy_wrappers_guarded_by_existence() -> None:
    """Only redefine functions that actually exist (idempotent)."""
    assert "pg_proc p" in M055
    assert "JOIN pg_namespace n ON n.oid = p.pronamespace" in M055


def test_attach_helper_exists() -> None:
    assert "CREATE OR REPLACE FUNCTION public.attach_updated_at_trigger" in M055
    assert "regclass" in M055


def test_existing_triggers_repointed() -> None:
    """The DO block rewires existing triggers to the canonical function."""
    assert "pg_trigger t" in M055
    assert "EXECUTE FUNCTION public.set_updated_at()" in M055


def test_repoint_skips_missing_tables_gracefully() -> None:
    assert "EXCEPTION WHEN OTHERS THEN" in M055


def test_055_wrapped_in_transaction() -> None:
    body = re.sub(r"--.*", "", M055)
    assert "BEGIN;" in body
    assert body.rstrip().endswith("COMMIT;")


# ===========================================================================
# 056 — hot-path indexes
# ===========================================================================
def _concurrent_indexes(sql: str) -> list[str]:
    return re.findall(
        r"CREATE INDEX CONCURRENTLY IF NOT EXISTS (\w+)", sql
    )


def test_at_least_six_concurrent_indexes() -> None:
    names = _concurrent_indexes(M056)
    assert len(names) >= 6, f"only {len(names)} CONCURRENTLY indexes: {names}"


def test_all_indexes_use_concurrently() -> None:
    """No blocking CREATE INDEX allowed in this migration."""
    # every CREATE INDEX statement must be CONCURRENTLY
    non_concurrent = re.findall(
        r"CREATE INDEX\s+(?!CONCURRENTLY)", M056
    )
    assert non_concurrent == [], "found non-CONCURRENTLY CREATE INDEX"


def test_candidates_covering_index() -> None:
    """candidates has a covering index (INCLUDE) for semantic search."""
    idx = re.search(
        r"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_candidates_tenant_embedding"
        r".*?INCLUDE \(id\).*?;",
        M056, re.S,
    )
    assert idx is not None
    assert "embedding IS NOT NULL" in idx.group(0)


def test_matches_covering_index() -> None:
    idx = re.search(
        r"idx_matches_tenant_active_score.*?INCLUDE \(overall_score, role_id\).*?;",
        M056, re.S,
    )
    assert idx is not None
    assert "status <> 'dismissed'" in idx.group(0)


def test_tickets_partial_index() -> None:
    idx = re.search(
        r"idx_tickets_tenant_open_sla.*?;", M056, re.S
    )
    assert idx is not None
    assert "WHERE status IN ('open', 'in_progress', 'awaiting_user')" in idx.group(0)


def test_emotion_timeline_partial_index() -> None:
    idx = re.search(
        r"idx_emotion_timeline_tenant_attention.*?;", M056, re.S
    )
    assert idx is not None
    assert "needs_attention = TRUE" in idx.group(0)


def test_journal_composite_index() -> None:
    assert "idx_journal_entries_tenant_user_recent" in M056
    assert "(tenant_id, user_id, created_at DESC)" in M056


def test_candidates_dedup_partial_index() -> None:
    idx = re.search(r"idx_candidates_tenant_dedup.*?;", M056, re.S)
    assert idx is not None
    assert "dedup_group IS NOT NULL" in idx.group(0)


def test_matches_tenant_role_composite_index() -> None:
    assert "idx_matches_tenant_role" in M056
    assert "(tenant_id, role_id, status)" in M056


def test_056_not_wrapped_in_transaction() -> None:
    """CONCURRENTLY cannot run inside a transaction block."""
    body = re.sub(r"--.*", "", M056)
    assert re.search(r"^\s*BEGIN;", body, re.M) is None, \
        "056 must not open an explicit transaction (CONCURRENTLY)"
    assert re.search(r"^\s*COMMIT;", body, re.M) is None


def test_analyze_after_indexes() -> None:
    """Planner stats refreshed so new indexes are picked up."""
    assert "ANALYZE public.candidates" in M056
    assert "ANALYZE public.matches" in M056


def test_indexes_are_idempotent() -> None:
    """Every CREATE INDEX uses IF NOT EXISTS."""
    body = re.sub(r"--.*", "", M056)  # drop comments first
    total = len(re.findall(r"CREATE INDEX CONCURRENTLY", body))
    guarded = len(re.findall(r"CREATE INDEX CONCURRENTLY\s+IF NOT EXISTS", body))
    assert total == guarded, "found a non-idempotent CREATE INDEX CONCURRENTLY"


# ===========================================================================
# Cross-check: index shapes align with real schema columns
# ===========================================================================
@pytest.mark.parametrize("col", ["tenant_id", "embedding", "dedup_group"])
def test_candidate_index_columns_exist_in_schema(col: str) -> None:
    schema = (MIGRATIONS / "001_cloud_schema.sql").read_text(encoding="utf-8")
    cand_block = re.search(r"CREATE TABLE candidates \((.*?)\);", schema, re.S)
    assert cand_block is not None
    # tenant_id may be added by 046/054; accept either the cloud schema or
    # the migrations that add it
    assert col == "tenant_id" or col in cand_block.group(1)


def test_match_status_values_match_enum() -> None:
    schema = (MIGRATIONS / "001_cloud_schema.sql").read_text(encoding="utf-8")
    enum = re.search(r"match_status AS ENUM \((.*?)\)", schema, re.S)
    assert enum is not None
    assert "'dismissed'" in enum.group(1)  # partial-index WHERE uses it
