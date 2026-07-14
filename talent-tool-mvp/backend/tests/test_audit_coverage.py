"""T5014 — Audit PII decorator coverage tests.

Validates that the AST-driven coverage scanner and the public
``services.platform.audit`` facade correctly:
  * detect PII-touching routes
  * report @audit_pii coverage as a percentage
  * auto-decorate untracked routes in memory
  * surface coverage via the security startup gate
"""
from __future__ import annotations

import os
import textwrap

import pytest

from services.platform.audit import (
    audit_pii,
    coverage_report,
    enforce_pii_decorator_coverage,
    scan_source_for_pii,
)


# ---------------------------------------------------------------------------
# Source-level AST scanner
# ---------------------------------------------------------------------------
def test_scan_source_detects_pii_params():
    src = textwrap.dedent(
        """
        def get_user(email: str, phone: str, name: str):
            return 1

        def unrelated(x: int):
            return x
        """
    )
    hits = scan_source_for_pii(src)
    names = {h.qualname for h in hits}
    assert "get_user" in names
    assert "unrelated" not in names
    pii = next(h for h in hits if h.qualname == "get_user").pii_params
    assert {"email", "phone", "name"} <= set(pii)


def test_scan_source_empty():
    assert scan_source_for_pii("") == []


# ---------------------------------------------------------------------------
# coverage_report against a synthetic api dir
# ---------------------------------------------------------------------------
@pytest.fixture()
def synthetic_api(tmp_path, monkeypatch):
    """Create a fake api dir with one audited + one unaudited PII route."""
    api = tmp_path / "api"
    api.mkdir()
    (api / "__init__.py").write_text("")
    (api / "audited.py").write_text(
        textwrap.dedent(
            """
            from fastapi import APIRouter
            from services.platform.audit import audit_pii
            router = APIRouter()

            @router.get("/u/{user_id}")
            @audit_pii("read", "user", pii_fields=["email"])
            def get_user(email: str):
                return {"email": email}
            """
        )
    )
    (api / "untracked.py").write_text(
        textwrap.dedent(
            """
            from fastapi import APIRouter
            router = APIRouter()

            @router.post("/u")
            def create_user(email: str, phone: str):
                return {}
            """
        )
    )
    # Make the tmp_path importable so `api.untracked` resolves, and chdir
    # there so os.path.relpath produces "api/untracked.py".
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return str(api)


def test_coverage_report_detects_mix(synthetic_api):
    rep = coverage_report(api_dir=synthetic_api)
    assert rep["total_pii_touching"] == 2
    assert rep["audited"] == 1
    assert rep["untracked"] == 1
    assert rep["coverage_pct"] == 50.0
    untracked_names = {d["function"] for d in rep["untracked_detail"]}
    assert untracked_names == {"create_user"}


def test_coverage_report_full_when_all_audited(tmp_path):
    api = tmp_path / "api"
    api.mkdir()
    (api / "a.py").write_text(
        textwrap.dedent(
            """
            from fastapi import APIRouter
            from services.platform.audit import audit_pii
            router = APIRouter()

            @router.get("/x")
            @audit_pii("read", "x")
            def f(email: str):
                return email
            """
        )
    )
    rep = coverage_report(api_dir=str(api))
    assert rep["coverage_pct"] == 100.0
    assert rep["untracked"] == 0


def test_enforce_coverage_returns_report(synthetic_api):
    rep = enforce_pii_decorator_coverage(api_dir=synthetic_api, min_coverage_pct=100.0)
    assert rep["coverage_pct"] == 50.0


def test_enforce_coverage_auto_decorates(synthetic_api, monkeypatch, tmp_path):
    # tmp_path is on sys.path so the `api` package resolves to the synthetic
    # one (the backend's own `api` package must not shadow it).
    monkeypatch.syspath_prepend(str(tmp_path))
    # Drop any previously-imported real `api` package so the synthetic wins.
    import sys
    sys.modules.pop("api", None)
    sys.modules.pop("api.untracked", None)
    rep = enforce_pii_decorator_coverage(
        api_dir="api", min_coverage_pct=100.0, auto_decorate=True
    )
    assert rep["untracked"] == 0
    assert rep["coverage_pct"] == 100.0


# ---------------------------------------------------------------------------
# Startup gate integration
# ---------------------------------------------------------------------------
def test_check_audit_coverage_non_fatal_under_threshold(monkeypatch, synthetic_api):
    monkeypatch.delenv("AUDIT_COVERAGE_STRICT", raising=False)
    from compliance.security_startup import check_audit_coverage

    rep = check_audit_coverage(api_dir=synthetic_api, min_coverage_pct=100.0)
    assert rep["coverage_pct"] < 100.0  # did not raise


def test_check_audit_coverage_fatal_when_strict(monkeypatch, synthetic_api):
    monkeypatch.setenv("AUDIT_COVERAGE_STRICT", "1")
    from compliance.security_startup import (
        SecurityStartupError,
        check_audit_coverage,
    )

    with pytest.raises(SecurityStartupError):
        check_audit_coverage(api_dir=synthetic_api, min_coverage_pct=100.0)


# ---------------------------------------------------------------------------
# Live @audit_pii behaviour
# ---------------------------------------------------------------------------
def test_audit_pii_decorator_records_access():
    from services.platform.audit_v2 import get_audit_store, reset_audit_store

    reset_audit_store()

    @audit_pii("read", "candidate", pii_fields=["email"])
    def fetch(email: str) -> dict:
        return {"email": email}

    fetch(email="a@b.com")
    store = get_audit_store()
    assert len(store) > 0
    rec = store.query(action="read", resource_type="candidate")[-1]
    assert "email" in rec.pii_accessed
    reset_audit_store()
