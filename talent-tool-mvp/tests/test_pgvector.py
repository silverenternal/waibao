"""T5012 — pgvector tuning migration tests (structural).

Validates ``057_pgvector_tuning.sql`` without a live Postgres:

* the lone IVFFlat index (company_policies) is replaced with HNSW
* all other embedding columns get a tuned HNSW index (m=16, ef_construction=64)
* ``hnsw.ef_search = 200`` is set as the database default (portably, via a DO
  block that resolves ``current_database()``)
* a ``set_vector_search_width(ef)`` helper exists and clamps to [1, 1000]
* no IVFFlat remains in the fleet after this migration
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[1] / "supabase" / "migrations"
M057 = (MIGRATIONS / "057_pgvector_tuning.sql").read_text(encoding="utf-8")


# ===========================================================================
# Extension
# ===========================================================================
def test_vector_extension_ensured() -> None:
    assert "CREATE EXTENSION IF NOT EXISTS vector" in M057


# ===========================================================================
# IVFFlat → HNSW migration
# ===========================================================================
def test_legacy_ivfflat_index_dropped() -> None:
    """The company_policies IVFFlat index must be removed first."""
    assert "DROP INDEX IF EXISTS public.company_policies_embedding_idx" in M057


def test_no_ivfflat_created_in_057() -> None:
    """This migration must not re-introduce IVFFlat anywhere."""
    assert "USING ivfflat" not in M057.lower().replace("ivfflat", "ivfflat")
    assert re.search(r"USING\s+ivfflat", M057, re.I) is None


def test_company_policies_gets_hnsw() -> None:
    idx = re.search(
        r"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_company_policies_embedding_hnsw.*?;",
        M057, re.S,
    )
    assert idx is not None
    assert "USING hnsw" in idx.group(0)
    assert "vector_cosine_ops" in idx.group(0)


# ===========================================================================
# HNSW tuning params across the fleet
# ===========================================================================
REQUIRED_HNSW_INDEXES = [
    "idx_candidates_embedding_hnsw",
    "idx_roles_embedding_hnsw",
    "idx_rag_chunks_embedding_hnsw",
    "idx_memories_v2_embedding_hnsw_tuned",
]


@pytest.mark.parametrize("name", REQUIRED_HNSW_INDEXES)
def test_tuned_hnsw_index_present(name: str) -> None:
    pattern = rf"CREATE INDEX CONCURRENTLY IF NOT EXISTS {re.escape(name)}.*?;"
    m = re.search(pattern, M057, re.S)
    assert m is not None, f"{name} missing from 057"
    body = m.group(0)
    assert "USING hnsw" in body
    assert "m = 16" in body
    assert "ef_construction = 64" in body


def test_all_hnsw_indexes_concurrent() -> None:
    """Every index build must be CONCURRENTLY (no write blocking)."""
    total = len(re.findall(r"CREATE INDEX", M057))
    concurrent = len(re.findall(r"CREATE INDEX CONCURRENTLY", M057))
    assert total == concurrent


def test_all_indexes_idempotent() -> None:
    body = re.sub(r"--.*", "", M057)
    total = len(re.findall(r"CREATE INDEX CONCURRENTLY", body))
    guarded = len(re.findall(r"CREATE INDEX CONCURRENTLY\s+IF NOT EXISTS", body))
    assert total == guarded


# ===========================================================================
# ef_search default
# ===========================================================================
def test_ef_search_set_to_200() -> None:
    """hnsw.ef_search = 200 set as the database default."""
    assert re.search(r"hnsw\.ef_search\s*=\s*200", M057) is not None


def test_ef_search_set_portably() -> None:
    """Uses current_database() so the migration is env-agnostic."""
    assert "current_database()" in M057
    assert "ALTER DATABASE %I SET hnsw.ef_search" in M057


def test_ef_search_failure_is_non_fatal() -> None:
    """The DO block swallows the error (RAISE NOTICE) so migration proceeds."""
    assert "EXCEPTION WHEN OTHERS THEN" in M057
    assert "RAISE NOTICE" in M057


# ===========================================================================
# set_vector_search_width helper
# ===========================================================================
def test_set_vector_search_width_helper_exists() -> None:
    assert "CREATE OR REPLACE FUNCTION public.set_vector_search_width" in M057
    assert "DEFAULT 200" in M057


def test_set_vector_search_width_clamps_range() -> None:
    """Out-of-range ef must raise 22023 (invalid_parameter_value)."""
    assert "ERRCODE = '22023'" in M057
    assert "out of range [1,1000]" in M057


def test_set_vector_search_width_uses_local_scope() -> None:
    """The GUC is set LOCAL (true) so it scopes to the transaction."""
    assert "set_config('hnsw.ef_search', ef::text, true)" in M057


# ===========================================================================
# Idempotency / no transaction
# ===========================================================================
def test_057_not_wrapped_in_transaction() -> None:
    """CONCURRENTLY cannot run inside a transaction block."""
    body = re.sub(r"--.*", "", M057)
    assert re.search(r"^\s*BEGIN;", body, re.M) is None
    assert re.search(r"^\s*COMMIT;", body, re.M) is None


def test_documentation_comment_present() -> None:
    assert "T5012" in M057
    assert "HNSW vector index" in M057


# ===========================================================================
# Cross-check: the replaced IVFFlat actually existed in the prior fleet
# ===========================================================================
def test_legacy_ivfflat_origin_confirmed() -> None:
    """company_policies originally used IVFFlat (migration 005)."""
    m005 = (MIGRATIONS / "005_company_knowledge.sql").read_text(encoding="utf-8")
    assert re.search(r"USING\s+ivfflat", m005, re.I) is not None
    assert "company_policies" in m005
