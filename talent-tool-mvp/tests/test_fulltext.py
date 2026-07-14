"""T5013 (part 2) — Chinese full-text search tests (structural).

Validates ``059_zhparser.sql`` without a live Postgres (zhparser may be
absent in CI, so the migration must degrade gracefully).

Coverage
--------
* zhparser extension creation is guarded (degrades to NOTICE on failure)
* a ``chinese_zh`` text-search config is created only when zhparser loaded
* ``enable_chinese_fts()`` adds a STORED generated tsvector + GIN index, and
  falls back to the ``simple`` config when zhparser is missing
* the migration fans out to candidates(cv_text/profile_text) + signals
* a ``chinese_tsquery(text)`` convenience helper exists
* the generated column uses ``to_tsvector`` with a runtime config selector
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[1] / "supabase" / "migrations"
M059 = (MIGRATIONS / "059_zhparser.sql").read_text(encoding="utf-8")


# ===========================================================================
# Extension + config (guarded)
# ===========================================================================
def test_zhparser_extension_guarded() -> None:
    """CREATE EXTENSION must not hard-fail when zhparser is unavailable."""
    assert "CREATE EXTENSION IF NOT EXISTS zhparser" in M059
    assert "EXCEPTION" in M059
    assert "WHEN insufficient_privilege OR undefined_file OR feature_not_supported" in M059


def test_chinese_zh_config_built_conditionally() -> None:
    """The config is only created when the extension actually loaded."""
    assert "CREATE TEXT SEARCH CONFIGURATION IF NOT EXISTS chinese_zh" in M059
    assert "PARSER = zhparser" in M059
    assert "IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'zhparser')" in M059


def test_config_has_token_mappings() -> None:
    assert "ADD MAPPING FOR n,v,a,i,e,l WITH simple" in M059


# ===========================================================================
# enable_chinese_fts helper
# ===========================================================================
def test_helper_exists() -> None:
    assert "CREATE OR REPLACE FUNCTION public.enable_chinese_fts" in M059


def test_helper_uses_stored_generated_column() -> None:
    """The tsvector is a STORED generated column (no trigger maintenance)."""
    assert "GENERATED ALWAYS AS" in M059
    assert "STORED" in M059


def test_helper_creates_gin_index() -> None:
    assert "USING GIN" in M059
    assert "idx_%s_%s_gin" in M059


def test_helper_falls_back_to_simple_config() -> None:
    """When zhparser is absent, use 'simple' so the column still exists."""
    assert "CASE WHEN" in M059
    assert "'chinese_zh'" in M059
    assert "'simple'" in M059


def test_helper_uses_to_tsvector() -> None:
    assert "to_tsvector(" in M059
    assert "coalesce(%I" in M059


def test_helper_idempotent() -> None:
    assert "CREATE INDEX IF NOT EXISTS" in M059
    assert "has_col" in M059  # skips re-adding an existing column


def test_helper_validates_table_exists() -> None:
    assert "table % not found" in M059


# ===========================================================================
# Fan-out to searchable tables
# ===========================================================================
@pytest.mark.parametrize(
    "table,col",
    [
        ("candidates", "cv_text"),
        ("candidates", "profile_text"),
        ("signals", "metadata::text"),
    ],
)
def test_searchable_targets_enumerated(table: str, col: str) -> None:
    assert table in M059
    assert col in M059


def test_fanout_guards_missing_table() -> None:
    """The fan-out DO block skips a table that does not exist."""
    assert "information_schema.tables" in M059


def test_fanout_guards_missing_column() -> None:
    assert "information_schema.columns" in M059


# ===========================================================================
# chinese_tsquery convenience helper
# ===========================================================================
def test_chinese_tsquery_exists() -> None:
    assert "CREATE OR REPLACE FUNCTION public.chinese_tsquery" in M059


def test_chinese_tsquery_returns_tsquery() -> None:
    assert "RETURNS tsquery" in M059


def test_chinese_tsquery_uses_plainto_tsquery() -> None:
    assert "plainto_tsquery(" in M059


def test_chinese_tsquery_config_selector() -> None:
    """Uses chinese_zh when available, else simple — same selector as the helper."""
    block = re.search(r"FUNCTION public\.chinese_tsquery.*?\$\$;", M059, re.S)
    assert block is not None
    body = block.group(0)
    assert "chinese_zh" in body
    assert "simple" in body


# ===========================================================================
# Documentation / structure
# ===========================================================================
def test_no_dynamic_sql_injection_smell() -> None:
    """enable_chinese_fts uses format() with %I/%L (no string concatenation)."""
    assert "format(" in M059
    assert "%I" in M059
    assert "%L" in M059


def test_t5013_anchor_in_docs() -> None:
    assert "T5013" in M059


def test_no_c_style_comments() -> None:
    """No stray // comments (they are invalid SQL)."""
    body = re.sub(r"--.*", "", M059)
    # ignore // inside string literals
    assert re.search(r"(?<!')//(?!')", body) is None or "//" not in body.replace("'//'", "")


# ===========================================================================
# Cross-check: the searchable columns actually exist in the schema
# ===========================================================================
def test_candidate_text_columns_exist() -> None:
    schema = (MIGRATIONS / "001_cloud_schema.sql").read_text(encoding="utf-8")
    assert "cv_text TEXT" in schema
    assert "profile_text TEXT" in schema
