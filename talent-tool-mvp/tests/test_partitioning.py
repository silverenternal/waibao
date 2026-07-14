"""T5013 (part 1) — monthly RANGE partitioning tests (structural).

Validates ``058_partitioning.sql`` without a live Postgres:

* a reusable ``create_monthly_partition(parent, year, month)`` helper exists
  and validates its arguments
* the three target tables are converted with the correct partition key:
  audit_log_v2/created_at, signals/created_at, funnel_events/occurred_at
* each swap renames the old table, creates a RANGE-partitioned parent, and
  moves the rows via INSERT...SELECT
* a DEFAULT partition + current/next-month partitions are created
* the helper is idempotent (CREATE TABLE IF NOT EXISTS)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[1] / "supabase" / "migrations"
M058 = (MIGRATIONS / "058_partitioning.sql").read_text(encoding="utf-8")


# ===========================================================================
# create_monthly_partition helper
# ===========================================================================
def test_helper_exists() -> None:
    assert "CREATE OR REPLACE FUNCTION public.create_monthly_partition" in M058


def test_helper_signature() -> None:
    assert "parent regclass" in M058
    assert "year integer" in M058
    assert "month integer" in M058


def test_helper_validates_month_range() -> None:
    assert "month < 1 OR month > 12" in M058
    assert "ERRCODE='22023'" in M058


def test_helper_validates_year_range() -> None:
    assert "year < 1970 OR year > 2999" in M058


def test_helper_resolves_partition_key_dynamically() -> None:
    """The helper reads the partition key from pg_partitioned_table (generic)."""
    assert "pg_partitioned_table pt" in M058
    assert "pt.partattrs[1]" in M058


def test_helper_idempotent() -> None:
    assert "CREATE TABLE IF NOT EXISTS" in M058
    assert "PARTITION OF" in M058


def test_helper_uses_make_timestamptz() -> None:
    assert "make_timestamptz(year, month, 1" in M058
    assert "interval '1 month'" in M058


# ===========================================================================
# Target table conversion
# ===========================================================================
@pytest.mark.parametrize(
    "table,ts_col",
    [
        ("audit_log_v2", "created_at"),
        ("signals", "created_at"),
        ("funnel_events", "occurred_at"),
    ],
)
def test_target_tables_partitioned(table: str, ts_col: str) -> None:
    block = re.search(
        rf"PARTITION BY RANGE \({re.escape(ts_col)}\)", M058
    )
    assert block is not None, f"no RANGE partitioning on {ts_col}"


def test_audit_log_v2_swap_present() -> None:
    assert "RENAME TO audit_log_v2_unpartitioned" in M058
    assert "PARTITION BY RANGE (created_at)" in M058


def test_signals_swap_present() -> None:
    assert "RENAME TO signals_unpartitioned" in M058


def test_funnel_events_swap_present() -> None:
    assert "RENAME TO funnel_events_unpartitioned" in M058
    assert "PARTITION BY RANGE (occurred_at)" in M058


def test_composite_pk_includes_partition_key() -> None:
    """Postgres requires the PK of a partitioned table to include the key."""
    assert "ADD PRIMARY KEY (id, created_at)" in M058
    assert "ADD PRIMARY KEY (id, occurred_at)" in M058


def test_old_pk_dropped_before_recreate() -> None:
    assert "DROP CONSTRAINT IF EXISTS audit_log_v2_pkey" in M058
    assert "DROP CONSTRAINT IF EXISTS signals_pkey" in M058


def test_data_moved_via_insert_select() -> None:
    """Rows are copied from the renamed heap into the new partitioned parent."""
    assert "INSERT INTO public.audit_log_v2" in M058
    assert "FROM public.audit_log_v2_unpartitioned" in M058
    assert "INSERT INTO public.signals" in M058
    assert "INSERT INTO public.funnel_events" in M058


def test_default_partition_created() -> None:
    """A DEFAULT partition catches any row outside the named ranges."""
    assert "audit_log_v2_default" in M058
    assert "PARTITION OF public.audit_log_v2 DEFAULT" in M058
    assert "PARTITION OF public.funnel_events DEFAULT" in M058


def test_current_and_next_month_partitions_seeded() -> None:
    """The migration creates this month + next month so inserts never miss."""
    assert "now()" in M058
    assert "now() + interval '1 month'" in M058


def test_like_including_all_for_column_copy() -> None:
    """The partitioned parent inherits all columns from the renamed heap."""
    assert "LIKE public.audit_log_v2_unpartitioned INCLUDING ALL" in M058


# ===========================================================================
# Idempotency
# ===========================================================================
def test_swap_is_idempotent() -> None:
    """Re-running detects an already-partitioned table and skips the swap."""
    assert "already partitioned" in M058
    assert "pg_partitioned_table" in M058


def test_missing_table_handled() -> None:
    """A table that does not exist yet is skipped, not error'd."""
    assert "missing — nothing to partition" in M058


def test_wrapped_in_transaction() -> None:
    body = re.sub(r"--.*", "", M058)
    assert "BEGIN;" in body
    assert body.rstrip().endswith("COMMIT;")


# ===========================================================================
# Hot indexes recreated on the parent
# ===========================================================================
def test_parent_indexes_recreated() -> None:
    assert "idx_audit_log_v2_tenant_time" in M058
    assert "idx_signals_created" in M058
    assert "idx_funnel_events_occurred" in M058


# ===========================================================================
# Cross-check against the source schema
# ===========================================================================
def test_target_timestamp_columns_exist_in_schema() -> None:
    schema = (MIGRATIONS / "047_audit_v2.sql").read_text(encoding="utf-8")
    assert "created_at timestamptz" in schema  # audit_log_v2 key
    schema1 = (MIGRATIONS / "001_cloud_schema.sql").read_text(encoding="utf-8")
    assert "created_at TIMESTAMPTZ" in schema1  # signals key
    schema24 = (MIGRATIONS / "024_funnel_events.sql").read_text(encoding="utf-8")
    assert "occurred_at" in schema24            # funnel_events key
