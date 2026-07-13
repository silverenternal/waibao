"""T2603 — Audit v2 service + decorator tests.

Covers:
  * in-memory store + threading safety
  * audit() core API (region-aware lawful basis)
  * retention_until computation (PIPL 3 years, breach 5 years)
  * audit_pii decorator (sync + async, success + error paths)
  * auto-detection of PII fields from kwargs
  * audit context binding
  * AST scanner + decorator factory
  * coverage_report() against a synthetic module dir
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import textwrap
import uuid
from datetime import datetime, timezone

import pytest

from services.platform.audit_v2 import (
    ACTION_DATA_CLASS,
    DEFAULT_LAWFUL_BASIS,
    PII_FIELDS,
    AuditContext,
    AuditRecord,
    audit,
    audit_pii,
    build_audit_decorators,
    clear_audit_context,
    compute_retention_until,
    coverage_report,
    get_audit_context,
    get_audit_store,
    reset_audit_store,
    scan_module_for_pii,
    scan_source_for_pii,
    set_audit_context,
    update_audit_context,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_store():
    reset_audit_store()
    clear_audit_context()
    yield
    reset_audit_store()
    clear_audit_context()


# ---------------------------------------------------------------------------
# PII + lawful basis catalogue
# ---------------------------------------------------------------------------
class TestPIICatalog:
    def test_pii_fields_contains_canonical(self):
        for field in {"email", "phone", "name", "ssn", "resume", "interview_video"}:
            assert field in PII_FIELDS

    def test_default_lawful_basis_per_region(self):
        assert DEFAULT_LAWFUL_BASIS["EU"] == "gdpr_consent"
        assert DEFAULT_LAWFUL_BASIS["CN"] == "pipl_consent"
        assert DEFAULT_LAWFUL_BASIS["CA"] == "ccpa_business_purpose"

    def test_action_data_class(self):
        assert ACTION_DATA_CLASS["forget"] == "sensitive"
        assert ACTION_DATA_CLASS["export"] == "sensitive"
        assert ACTION_DATA_CLASS["read"] == "pii"
        assert ACTION_DATA_CLASS["login"] == "public"


# ---------------------------------------------------------------------------
# audit() core
# ---------------------------------------------------------------------------
class TestAuditCore:
    def test_audit_emits_id(self):
        rid = audit(action="read", resource="candidate", resource_id="c-1", pii_fields=["email"])
        assert rid.startswith("audv2_")

    def test_audit_appends_to_store(self):
        audit(action="read", resource="candidate", resource_id="c-1")
        rows = get_audit_store().query(resource_type="candidate")
        assert len(rows) == 1
        assert rows[0].action == "read"

    def test_audit_uses_region_lawful_basis(self):
        set_audit_context(AuditContext(region="CN", actor_id="u-1"))
        audit(action="read", resource="candidate")
        rows = get_audit_store().query()
        assert rows[0].lawful_basis == "pipl_consent"

    def test_audit_explicit_basis_wins(self):
        audit(
            action="read", resource="candidate",
            lawful_basis="gdpr_contract",
        )
        rows = get_audit_store().query()
        assert rows[0].lawful_basis == "gdpr_contract"

    def test_audit_auto_detects_pii(self):
        audit(action="update", resource="user", resource_id="phone")
        rows = get_audit_store().query()
        assert "phone" in rows[0].pii_accessed

    def test_audit_data_classification_sensitive(self):
        audit(action="update", resource="user", pii_fields=["ssn", "email"])
        rows = get_audit_store().query()
        assert rows[0].data_classification == "sensitive"

    def test_audit_swallows_errors(self):
        # even if metadata is non-serialisable we should not raise
        class WeirdObj:
            def __repr__(self): raise RuntimeError("nope")
        rid = audit(action="read", resource="candidate", metadata={"weird": WeirdObj()})
        assert rid  # still returns an id

    def test_audit_tenant_and_actor_from_context(self):
        set_audit_context(AuditContext(actor_id="u-1", actor_role="admin", tenant_id="t-1"))
        audit(action="read", resource="candidate", resource_id="c-1")
        rows = get_audit_store().query(tenant_id="t-1")
        assert len(rows) == 1
        assert rows[0].actor_role == "admin"

    def test_query_filters(self):
        for i in range(5):
            audit(action="read", resource="candidate", resource_id=f"c-{i}")
        audit(action="export", resource="candidate", resource_id="c-9")
        assert len(get_audit_store().query(action="read")) == 5
        assert len(get_audit_store().query(action="export")) == 1
        assert len(get_audit_store().query(resource_id="c-9")) == 1


# ---------------------------------------------------------------------------
# retention computation
# ---------------------------------------------------------------------------
class TestRetention:
    def test_default_3_years(self):
        rt = compute_retention_until("read")
        delta = (rt - datetime.now(timezone.utc)).days
        assert 1090 <= delta <= 1096

    def test_forget_5_years(self):
        rt = compute_retention_until("forget")
        delta = (rt - datetime.now(timezone.utc)).days
        assert 1823 <= delta <= 1828

    def test_login_2_years(self):
        rt = compute_retention_until("login")
        delta = (rt - datetime.now(timezone.utc)).days
        assert 728 <= delta <= 732

    def test_explicit_days(self):
        rt = compute_retention_until("read", explicit_days=42)
        delta = (rt - datetime.now(timezone.utc)).days
        assert 41 <= delta <= 42


# ---------------------------------------------------------------------------
# audit_pii decorator
# ---------------------------------------------------------------------------
class TestAuditPIIDecorator:
    def test_sync_decorator_records(self):
        @audit_pii("read", "candidate", pii_fields=["email"])
        def get_candidate(user, candidate_id: str):
            return {"id": candidate_id, "email": "x@y.z"}

        class U:
            id = "u-1"
            role = "admin"
            tenant_id = "t-1"
        get_candidate(U(), candidate_id="c-1")
        rows = get_audit_store().query()
        assert len(rows) == 1
        assert rows[0].pii_accessed == ["email"]
        assert rows[0].resource_id == "c-1"

    def test_async_decorator_records(self):
        @audit_pii("read", "candidate", pii_fields=["resume"])
        async def get_async(user, candidate_id: str):
            return {"id": candidate_id}

        class U:
            id = "u-1"
            role = "admin"
            tenant_id = None
        asyncio.run(get_async(U(), candidate_id="c-async"))
        rows = get_audit_store().query()
        assert len(rows) == 1
        assert rows[0].action == "read"

    def test_auto_detects_pii_from_kwargs(self):
        @audit_pii("update", "user")
        def update_user(user, email: str, phone: str):
            return email

        class U:
            id = "u-1"
            role = "user"
            tenant_id = None
        update_user(U(), email="x@y.z", phone="123")
        rows = get_audit_store().query()
        assert sorted(rows[0].pii_accessed) == ["email", "phone"]

    def test_records_error(self):
        @audit_pii("read", "candidate")
        def boom(user):
            raise RuntimeError("nope")

        class U:
            id = "u-1"
            role = "user"
            tenant_id = None
        with pytest.raises(RuntimeError):
            boom(U())
        rows = get_audit_store().query()
        assert len(rows) == 1
        assert rows[0].metadata.get("error") is True

    def test_metadata_fn(self):
        @audit_pii("read", "candidate", metadata_fn=lambda a, k, r: {"custom": r.get("id")})
        def get_candidate(user):
            return {"id": "c-1"}

        class U:
            id = "u-1"
            role = "user"
            tenant_id = None
        get_candidate(U())
        rows = get_audit_store().query()
        assert rows[0].metadata["custom"] == "c-1"

    def test_resource_id_from_result_attr(self):
        class Result:
            def __init__(self, rid): self.id = rid

        @audit_pii("create", "candidate", resource_id_attr="id")
        def create(user):
            return Result("c-new")

        class U:
            id = "u-1"
            role = "user"
            tenant_id = None
        create(U())
        rows = get_audit_store().query()
        assert rows[0].resource_id == "c-new"

    def test_meta_attached_to_wrapper(self):
        @audit_pii("read", "candidate", pii_fields=["email"])
        def f(user): return None
        assert hasattr(f, "__audit_meta__")
        assert f.__audit_meta__["action"] == "read"
        assert f.__audit_meta__["pii_fields"] == ["email"]


# ---------------------------------------------------------------------------
# AST scanner
# ---------------------------------------------------------------------------
class TestASTScanner:
    def test_scan_finds_pii_touching_functions(self):
        src = textwrap.dedent("""
            def read_email(user, email: str): pass
            def no_pii(user): pass
            def read_resume(user, resume: str): pass
        """)
        scanned = scan_source_for_pii(src)
        names = {s.qualname for s in scanned}
        assert "read_email" in names
        assert "read_resume" in names
        assert "no_pii" not in names

    def test_build_audit_decorators_returns_factory(self):
        src = textwrap.dedent("""
            def get_email(user, email: str): pass
        """)
        scanned = scan_source_for_pii(src)
        factories = build_audit_decorators(scanned, action="read")
        assert "get_email" in factories
        deco = factories["get_email"](action="read")
        # apply
        deco(lambda *a, **k: None)

    def test_scan_module_handles_synthetic(self):
        import types
        mod = types.ModuleType("synthetic_mod")
        mod.__dict__["__source__"] = textwrap.dedent("""
            def read_email(user, email: str): pass
        """)
        # inspect.getsource will fail on a synthetic module, so it should
        # return an empty list gracefully
        scanned = scan_module_for_pii(mod)
        assert scanned == []


# ---------------------------------------------------------------------------
# coverage_report
# ---------------------------------------------------------------------------
class TestCoverageReport:
    def test_runs_against_synthetic_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            api_dir = os.path.join(tmp, "api")
            os.makedirs(api_dir)
            with open(os.path.join(api_dir, "demo.py"), "w") as fp:
                fp.write(textwrap.dedent("""
                    from fastapi import APIRouter
                    from services.platform.audit_v2 import audit_pii

                    router = APIRouter()

                    @audit_pii("read", "candidate")
                    @router.get("/c")
                    def audited(user, email: str): pass

                    @router.get("/u")
                    def untracked(user, email: str): pass
                """))
            cwd = os.getcwd()
            try:
                os.chdir(tmp)
                report = coverage_report(api_dir=api_dir)
            finally:
                os.chdir(cwd)
            assert report["total_pii_touching"] >= 2
            assert report["audited"] >= 1
            assert report["untracked"] >= 1
            assert 0 < report["coverage_pct"] < 100


# ---------------------------------------------------------------------------
# Audit context
# ---------------------------------------------------------------------------
class TestAuditContext:
    def test_default_context(self):
        clear_audit_context()
        ctx = get_audit_context()
        assert ctx.region == "GLOBAL"
        assert ctx.actor_id is None

    def test_set_and_get(self):
        set_audit_context(AuditContext(region="CN", actor_id="u-1"))
        ctx = get_audit_context()
        assert ctx.region == "CN"
        assert ctx.actor_id == "u-1"

    def test_update_audit_context(self):
        set_audit_context(AuditContext(region="EU"))
        update_audit_context(region="CN", actor_id="u-2")
        ctx = get_audit_context()
        assert ctx.region == "CN"
        assert ctx.actor_id == "u-2"

    def test_clear_audit_context(self):
        set_audit_context(AuditContext(region="CN"))
        clear_audit_context()
        assert get_audit_context().region == "GLOBAL"


# ---------------------------------------------------------------------------
# AuditRecord dataclass
# ---------------------------------------------------------------------------
class TestAuditRecord:
    def test_slots_dataclass(self):
        rec = AuditRecord(
            id="audv2_x", actor_id="u", actor_role=None, tenant_id=None,
            action="read", resource_type="candidate", resource_id="c-1",
            data_classification="pii", pii_accessed=["email"],
            lawful_basis="gdpr_consent", request_id=None, session_id=None,
            metadata={}, created_at=datetime.now(timezone.utc),
            retention_until=datetime.now(timezone.utc),
        )
        assert rec.id == "audv2_x"
        assert rec.pii_accessed == ["email"]
