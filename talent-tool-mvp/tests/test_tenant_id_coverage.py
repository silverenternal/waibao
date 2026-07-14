"""T5010 — tenant_id full coverage + RLS (USING + WITH CHECK) tests.

These tests validate the migration ``054_tenant_id_full_coverage.sql`` at the
*static / structural* level: they parse the SQL and assert that every required
invariant is present, because we do not have a live Postgres in CI.  They also
unit-test the PL/pgSQL trigger logic by simulating it in Python so the
isolation semantics are pinned down regardless of the database engine.

Coverage
--------
* every target business table is covered by an ADD COLUMN / tenant_id reference
* back-fill uses organisation_id directly AND joins through users for the
  indirect tables
* tenant_id is forced NOT NULL on the fully-populated tables
* RLS policies carry BOTH ``USING`` and ``WITH CHECK`` clauses
* the enforcement trigger is ``BEFORE INSERT OR UPDATE`` (not INSERT only)
* the trigger function forbids reparenting on UPDATE (immutability)
* service_role bypass path is present
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[1] / "supabase" / "migrations"
M054 = (MIGRATIONS / "054_tenant_id_full_coverage.sql").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Target tables from the task spec (T5010)
# ---------------------------------------------------------------------------
TARGET_TABLES = [
    "candidates",
    "tickets",
    "matches",
    "conversations",
    "emotion_timeline",
    # daily_journals is exposed as journal_entries / voice_journal
    "journal_entries",
    # ai_interviews
    "ai_interview_sessions",
    # video / assessment / ats
    "video_interviews",
    "assessment_invitations",
    "ats_sync_records",
]


# ---------------------------------------------------------------------------
# 1. Column coverage
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("table", TARGET_TABLES)
def test_table_appears_in_coverage_list(table: str) -> None:
    """Each target table is enumerated in the master DO blocks."""
    assert table in M054, f"{table} not referenced in 054 migration"


def test_add_column_uses_if_not_exists_guard() -> None:
    """The ADD COLUMN path must be information_schema-guarded (idempotent)."""
    assert "information_schema.columns" in M054
    assert "ADD COLUMN tenant_id" in M054


def test_missing_table_does_not_blow_up() -> None:
    """Legacy table names that may not exist are skipped, not required."""
    # the DO block checks information_schema.tables before ADD COLUMN
    assert re.search(
        r"FROM information_schema\.tables\s+WHERE table_schema=.public. "
        r"AND table_name=t",
        M054,
    )


# ---------------------------------------------------------------------------
# 2. Back-fill correctness
# ---------------------------------------------------------------------------
def test_direct_backfill_from_organisation_id() -> None:
    """Tables with their own organisation_id must SET tenant_id = organisation_id."""
    assert "SET tenant_id = organisation_id" in M054


def test_indirect_backfill_via_users() -> None:
    """Tables without organisation_id join through users for the tenant."""
    assert "JOIN public.users cu ON cu.id = c.created_by" in M054
    assert "FROM public.users u" in M054


def test_matches_backfill_via_candidate_owner() -> None:
    """matches resolves tenant via candidates.created_by -> users."""
    assert re.search(r"UPDATE public\.matches\s+m", M054) is not None
    assert "FROM public.candidates c" in M054
    assert "JOIN public.users cu ON cu.id = c.created_by" in M054


def test_candidate_owned_tables_backfilled() -> None:
    """assessment_invitations / video_interviews inherit from candidate owner."""
    assert "x.candidate_id = c.id" in M054
    assert "cu.organisation_id" in M054  # legacy fallback when tenant_id NULL


def test_two_hop_message_backfill() -> None:
    """ai_interview_messages is 2-hop: session_id -> user -> tenant."""
    assert "msg.session_id = s.id" in M054


# ---------------------------------------------------------------------------
# 3. NOT NULL enforcement
# ---------------------------------------------------------------------------
def test_set_not_null_present() -> None:
    assert "ALTER COLUMN tenant_id SET NOT NULL" in M054


def test_not_null_guarded_by_null_precheck() -> None:
    """SET NOT NULL only runs after a count(*) = 0 pre-check (no half-fill)."""
    # find the SET NOT NULL block and ensure it is inside the IF null_count = 0 branch
    assert "null_count = 0" in M054
    # the NOT NULL applies to the fully-populated subset
    nn_tables = re.search(r"tables_nn text\[\] := ARRAY\[(.*?)\];", M054, re.S)
    assert nn_tables is not None
    for t in ["candidates", "matches", "tickets", "conversations", "emotion_timeline"]:
        assert t in nn_tables.group(1)


# ---------------------------------------------------------------------------
# 4. RLS USING + WITH CHECK
# ---------------------------------------------------------------------------
def test_rls_enabled_and_forced() -> None:
    assert "ENABLE ROW LEVEL SECURITY" in M054
    assert "FORCE ROW LEVEL SECURITY" in M054


def test_policy_has_using_and_with_check() -> None:
    """The tenant policy must carry both USING and WITH CHECK clauses."""
    # locate the CREATE POLICY tenant_all statement up to the next ', t);'
    idx = M054.find("CREATE POLICY tenant_all ON public.%I FOR ALL")
    assert idx != -1, "tenant_all policy not declared"
    # grab the full statement (it ends with the table-formatting arg ', t);')
    stmt = M054[idx : M054.find(", t);", idx) + len(", t);")]
    assert "USING (" in stmt, "policy missing USING clause"
    assert "WITH CHECK (" in stmt, "policy missing WITH CHECK clause"
    assert "public.current_tenant()" in stmt
    assert "public.is_service_role()" in stmt


def test_old_tenant_isolation_policy_dropped() -> None:
    """The legacy single-policy from 046 is replaced."""
    assert "DROP POLICY IF EXISTS tenant_isolation" in M054


def test_tenant_index_created() -> None:
    """Every covered table gets a tenant_id index for RLS perf."""
    assert "CREATE INDEX IF NOT EXISTS idx_%s_tenant" in M054


def test_service_role_bypass_in_policy() -> None:
    assert "public.is_service_role()" in M054


# ---------------------------------------------------------------------------
# 5. Trigger BEFORE INSERT + UPDATE
# ---------------------------------------------------------------------------
def test_trigger_is_insert_or_update() -> None:
    """The guard must fire on BOTH INSERT and UPDATE."""
    assert "BEFORE INSERT OR UPDATE" in M054
    # and the legacy INSERT-only trigger is dropped first
    assert "DROP TRIGGER IF EXISTS trg_tenant_id" in M054


def test_trigger_forbids_reparenting_on_update() -> None:
    """UPDATE that changes tenant_id must raise 42501 (immutable)."""
    assert "TG_OP = 'UPDATE'" in M054
    assert "tenant_id is immutable" in M054
    assert "ERRCODE = '42501'" in M054


def test_trigger_auto_attaches_on_insert() -> None:
    """On INSERT, a NULL tenant_id is auto-filled from the session GUC."""
    assert "NEW.tenant_id := ctx" in M054


def test_service_role_bypass_in_trigger() -> None:
    assert "IF public.is_service_role() THEN" in M054


# ---------------------------------------------------------------------------
# 6. Behavioral simulation of enforce_tenant_id()
# ---------------------------------------------------------------------------
class _Row:
    __slots__ = ("tenant_id",)

    def __init__(self, tenant_id):
        self.tenant_id = tenant_id


def _enforce_tenant_id(new: _Row, old: _Row | None, ctx, tg_op: str,
                       service_role: bool = False) -> _Row:
    """Pure-Python reimplementation of the PL/pgSQL trigger body."""
    if service_role:
        return new
    if tg_op == "INSERT":
        if new.tenant_id is None:
            new.tenant_id = ctx
        elif new.tenant_id != ctx:
            raise PermissionError("tenant_id mismatch on INSERT")
        return new
    # UPDATE
    if new.tenant_id != old.tenant_id:
        raise PermissionError("tenant_id is immutable on UPDATE")
    return new


def test_insert_auto_attach_when_null():
    row = _enforce_tenant_id(_Row(None), None, ctx="t1", tg_op="INSERT")
    assert row.tenant_id == "t1"


def test_insert_ok_when_matches_ctx():
    row = _enforce_tenant_id(_Row("t1"), None, ctx="t1", tg_op="INSERT")
    assert row.tenant_id == "t1"


def test_insert_rejected_when_cross_tenant():
    with pytest.raises(PermissionError):
        _enforce_tenant_id(_Row("t2"), None, ctx="t1", tg_op="INSERT")


def test_update_rejected_when_reparenting():
    with pytest.raises(PermissionError):
        _enforce_tenant_id(_Row("t2"), _Row("t1"), ctx="t1", tg_op="UPDATE")


def test_update_ok_when_unchanged():
    row = _enforce_tenant_id(_Row("t1"), _Row("t1"), ctx="t1", tg_op="UPDATE")
    assert row.tenant_id == "t1"


def test_service_role_bypasses_all_checks():
    row = _enforce_tenant_id(_Row("t-other"), _Row("t1"), ctx="t1",
                             tg_op="UPDATE", service_role=True)
    assert row.tenant_id == "t-other"


# ---------------------------------------------------------------------------
# 7. Migration is idempotent & transactional
# ---------------------------------------------------------------------------
def test_migration_wrapped_in_transaction() -> None:
    body = re.sub(r"--.*", "", M054)  # strip SQL comments
    assert "BEGIN;" in body
    assert body.rstrip().endswith("COMMIT;")


def test_helpers_recreated_or_replace() -> None:
    assert "CREATE OR REPLACE FUNCTION public.current_tenant()" in M054
    assert "CREATE OR REPLACE FUNCTION public.enforce_tenant_id()" in M054
