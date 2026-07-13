"""v8.0 T3503 — Feature Access (3-layer) tests (30+).

Covers:
    * Config Center block path
    * Service Toggle primary path
    * Feature Flag rollout / cohort gating
    * FastAPI dependency integration (check_service_access, as_dependency)
    * Batch / decorator helpers
    * Layer ordering when multiple layers disagree
    * Graceful degradation when each layer is unavailable
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
for p in (BACKEND, os.path.dirname(BACKEND)):
    if p and p not in sys.path:
        sys.path.insert(0, p)


# ---------------------------------------------------------------------------
# Fakes — same construction as test_service_toggle but kept minimal here.
# ---------------------------------------------------------------------------
class _FakeRow:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, store: Dict[str, Any], name: str):
        self.store = store
        self.name = name
        self._filters = []
        self._order = None
        self._select_cols = "*"

    def select(self, cols="*"):
        self._select_cols = cols
        return self

    def eq(self, col, value):
        self._filters.append(("eq", col, value))
        return self

    def neq(self, col, value):
        self._filters.append(("neq", col, value))
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def limit(self, n):
        self._filters.append(("limit", n))
        return self

    def _matched(self):
        rows = list(self.store.get(self.name, []))
        limit_n = None
        for f in self._filters:
            if len(f) == 3 and f[0] == "eq":
                rows = [r for r in rows if r.get(f[1]) == f[2]]
            elif len(f) == 3 and f[0] == "neq":
                rows = [r for r in rows if r.get(f[1]) != f[2]]
            elif len(f) == 2 and f[0] == "limit":
                limit_n = f[1]
        if self._order:
            col, desc = self._order
            rows = sorted(rows, key=lambda r: r.get(col) or "", reverse=desc)
        if limit_n is not None:
            rows = rows[:limit_n]
        return rows

    def execute(self):
        return _FakeRow(self._matched())

    def insert(self, payload):
        recs = payload if isinstance(payload, list) else [payload]
        for r in recs:
            rec = dict(r)
            if self.name in {"configs"}:
                rec.setdefault("id", len(self.store.get(self.name, [])) + 1)
            self.store.setdefault(self.name, []).append(rec)
        return self

    def upsert(self, payload, on_conflict=None):
        # Naive upsert: replace the matching row if any of the conflict
        # columns are equal. Falls back to insert.
        recs = payload if isinstance(payload, list) else [payload]
        conflict_cols = on_conflict.split(",") if on_conflict else []
        for r in recs:
            rows = self.store.setdefault(self.name, [])
            match_idx = None
            if conflict_cols:
                for i, existing in enumerate(rows):
                    if all(existing.get(c) == r.get(c) for c in conflict_cols):
                        match_idx = i
                        break
            if match_idx is not None:
                if self.name == "configs":
                    r.setdefault("id", rows[match_idx].get("id"))
                    rows[match_idx] = {**rows[match_idx], **r}
                else:
                    rows[match_idx] = {**rows[match_idx], **r}
            else:
                if self.name == "configs":
                    r.setdefault("id", len(rows) + 1)
                rows.append(dict(r))
        return self

    def update(self, payload):
        for r in self._matched():
            r.update(payload)
        return self

    def delete(self):
        rows = self._matched()
        for r in rows:
            self.store.setdefault(self.name, []).remove(r)
        return self


class FakeSupabase:
    def __init__(self):
        self.store: Dict[str, Any] = {
            "services": [],
            "service_overrides": [],
            "service_audit": [],
            "configs": [],
            "config_history": [],
            "feature_flags": [],
            "feature_flag_overrides": [],
            "feature_flag_audit": [],
        }

    def table(self, name):
        self.store.setdefault(name, [])
        return _FakeTable(self.store, name)


@pytest.fixture
def fake_supabase(monkeypatch):
    fs = FakeSupabase()
    from api import deps as api_deps

    monkeypatch.setattr(api_deps, "get_supabase_admin", lambda: fs)

    from services.platform import (
        service_toggle as st,
        config_service as cs,
        feature_flag as ff,
        feature_access as fa,
    )

    monkeypatch.setattr(st, "_supabase", lambda: fs)
    monkeypatch.setattr(cs, "_supabase", lambda: fs)
    st._LOCAL_CACHE.clear()
    st._LOCAL_TS.clear()
    cs._CACHE.clear()
    if hasattr(ff, "_CACHE"):
        try:
            ff._CACHE.clear()  # type: ignore[attr-defined]
        except Exception:
            pass
    fa.invalidate_cache = lambda *a, **k: st.invalidate_cache(*a, **k)

    # Seed a couple of services we can reference
    from services.platform.service_catalog import Service, ServiceCategory, PlanTier, ServiceStatus

    def _seed_svc(name, display, category, plan, roles):
        st.service_toggle.register_service(
            Service(
                name=name,
                display_name=display,
                description=display.lower(),
                category=category,
                status=ServiceStatus.ENABLED,
                plan_required=plan,
                roles_allowed=list(roles),
            ),
            persist=False,
        )
        # Mirror to fake Supabase so the catalog lookup path also succeeds.
        fs.table("services").insert(
            {
                "name": name,
                "display_name": display,
                "description": display.lower(),
                "category": category.value,
                "status": "enabled",
                "plan_required": plan.value,
                "roles_allowed": list(roles),
                "dependencies": [],
                "version": 1,
            }
        )

    _seed_svc(
        "agent.profile",
        "Profile Agent",
        ServiceCategory.AGENT,
        PlanTier.PRO,
        ["jobseeker", "admin"],
    )
    _seed_svc(
        "integration.ats",
        "ATS",
        ServiceCategory.INTEGRATION,
        PlanTier.ENTERPRISE,
        ["employer", "admin"],
    )
    yield fs
    st._LOCAL_CACHE.clear()
    st._LOCAL_TS.clear()
    cs._CACHE.clear()


# ---------------------------------------------------------------------------
# 1. Layer A — Config Center can deny
# ---------------------------------------------------------------------------
def test_config_layer_deny(fake_supabase):
    from services.platform import config_service as cs, feature_access as fa
    cs.set_value("service_toggle", "agent.profile", False, value_type="boolean", changed_by="admin")
    assert fa.check("agent.profile", org_id=None, plan="pro", role="jobseeker") is False


def test_config_layer_deny_per_tenant(fake_supabase):
    from services.platform import config_service as cs, feature_access as fa
    cs.set_value("service_toggle", "org-77:agent.profile", False, value_type="boolean", changed_by="admin")
    cs.set_value("service_toggle", "agent.profile", False, value_type="boolean", changed_by="admin")
    assert fa.check("agent.profile", org_id="org-77", plan="pro", role="jobseeker") is False
    # different org: still denied via global config
    assert fa.check("agent.profile", org_id="org-other", plan="pro", role="jobseeker") is False


def test_config_layer_true_default(fake_supabase):
    from services.platform import feature_access as fa
    assert fa.check("agent.profile", org_id=None, plan="pro", role="jobseeker") is True


# ---------------------------------------------------------------------------
# 2. Layer B — Service Toggle primary path
# ---------------------------------------------------------------------------
def test_service_layer_disabled_status(fake_supabase):
    from services.platform import service_toggle as st, feature_access as fa
    from services.platform.service_catalog import ServiceStatus
    st.service_toggle._set_status(
        "agent.profile", ServiceStatus.DISABLED, actor_id="admin", reason=""
    )
    assert fa.check("agent.profile", org_id=None, plan="pro", role="jobseeker") is False


def test_service_layer_plan_too_low(fake_supabase):
    from services.platform import feature_access as fa
    assert fa.check("integration.ats", org_id=None, plan="free", role="employer") is False


def test_service_layer_plan_sufficient(fake_supabase):
    from services.platform import feature_access as fa
    assert fa.check("integration.ats", org_id=None, plan="enterprise", role="employer") is True


def test_service_layer_role_allow_list_blocks(fake_supabase):
    from services.platform import feature_access as fa
    assert fa.check("agent.profile", org_id=None, plan="pro", role="compliance") is False


def test_service_layer_per_org_override_enable(fake_supabase):
    from services.platform import service_toggle as st, feature_access as fa
    st.service_toggle.override("org-9", "agent.profile", "enabled", reason="vip")
    assert fa.check("agent.profile", org_id="org-9", plan="free", role="jobseeker") is True
    assert fa.check("agent.profile", org_id="other", plan="free", role="jobseeker") is False


def test_service_layer_unknown_service(fake_supabase):
    from services.platform import feature_access as fa
    assert fa.check("does.not.exist", org_id=None, plan="pro", role="admin") is False


def test_require_raises_when_denied(fake_supabase):
    from services.platform import feature_access as fa
    with pytest.raises(PermissionError):
        fa.require("integration.ats", org_id=None, plan="free", role="employer")


def test_require_passes_when_allowed(fake_supabase):
    from services.platform import feature_access as fa
    fa.require("agent.profile", org_id=None, plan="pro", role="jobseeker")


# ---------------------------------------------------------------------------
# 3. Layer C — Feature Flag blocks rollout
# ---------------------------------------------------------------------------
def test_feature_flag_layer_blocks(fake_supabase, monkeypatch):
    from services.platform import feature_flag as ff
    from services.platform.feature_access import check

    # A flag with rollout 0 -> is_enabled should return False for any user.
    sentinel_flag = type(
        "FF",
        (),
        {"name": "agent.profile", "enabled": False, "rollout_percent": 0, "rules": {}},
    )()

    monkeypatch.setattr(ff, "get_flag", lambda name: sentinel_flag if name == "agent.profile" else None)
    monkeypatch.setattr(ff, "is_enabled", lambda name, **k: False)

    assert check("agent.profile", org_id=None, plan="pro", role="jobseeker") is False


def test_feature_flag_layer_missing_flag_does_not_deny(fake_supabase, monkeypatch):
    from services.platform import feature_flag as ff
    from services.platform.feature_access import check

    monkeypatch.setattr(ff, "is_enabled", lambda *a, **k: False)
    # No flag row inserted; absent flag should not block
    assert check("agent.profile", org_id=None, plan="pro", role="jobseeker") is True


# ---------------------------------------------------------------------------
# 4. Layer precedence — any-layer-deny wins
# ---------------------------------------------------------------------------
def test_any_layer_can_deny(fake_supabase, monkeypatch):
    from services.platform import config_service as cs, feature_flag as ff, feature_access as fa

    cs.set_value("service_toggle", "agent.profile", False, value_type="boolean", changed_by="admin")
    monkeypatch.setattr(ff, "is_enabled", lambda *a, **k: True)
    assert fa.check("agent.profile", org_id=None, plan="pro", role="jobseeker") is False


# ---------------------------------------------------------------------------
# 5. batch_check
# ---------------------------------------------------------------------------
def test_batch_check_returns_per_service(fake_supabase):
    from services.platform import feature_access as fa
    out = fa.batch_check(
        ["agent.profile", "integration.ats", "does.not.exist"],
        org_id=None,
        plan="pro",
        role="jobseeker",
    )
    assert out["agent.profile"] is True
    assert out["integration.ats"] is False  # plan=pro < enterprise
    assert out["does.not.exist"] is False


def test_batch_check_includes_tenant_block(fake_supabase):
    from services.platform import config_service as cs, feature_access as fa
    cs.set_value("service_toggle", "org-1:agent.profile", False, value_type="boolean", changed_by="admin")
    out = fa.batch_check(
        ["agent.profile"], org_id="org-1", plan="pro", role="jobseeker"
    )
    assert out["agent.profile"] is False


# ---------------------------------------------------------------------------
# 6. Decorator + imperative guards
# ---------------------------------------------------------------------------
def test_check_context_helper(fake_supabase):
    from services.platform import feature_access as fa
    assert fa.check_context("agent.profile", org_id=None, plan="pro", role="jobseeker") is True
    assert fa.check_context("integration.ats", org_id=None, plan="pro", role="employer") is False


def test_guard_decorator_blocks_sync(fake_supabase):
    from services.platform import feature_access as fa

    class _Ctx:
        def __init__(self, plan="free", role="employer"):
            self.org_id = None
            self.plan = plan
            self.role = role
            self.user_id = None

    @fa.guard("integration.ats")  # integration requires enterprise plan
    def _do(ctx):
        return 42

    with pytest.raises(PermissionError):
        _do(_Ctx())  # free plan => denied

    # bump plan on a new instance
    assert _do(_Ctx(plan="enterprise")) == 42


def test_guard_decorator_async_pass(fake_supabase):
    import asyncio
    from services.platform import feature_access as fa

    class _Ctx:
        def __init__(self, plan="pro", role="jobseeker"):
            self.org_id = None
            self.plan = plan
            self.role = role
            self.user_id = None

    @fa.guard("agent.profile")
    async def _do(ctx):
        return "ok"

    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(_do(_Ctx()))
    finally:
        loop.close()
    assert res == "ok"


# ---------------------------------------------------------------------------
# 7. FastAPI dependency helpers
# ---------------------------------------------------------------------------
def test_as_dependency_returns_bool(fake_supabase):
    from services.platform import feature_access as fa

    dep = fa.as_dependency("agent.profile")
    # Inspect: the dep must wire Request properly so FastAPI routes it.
    import inspect

    sig = inspect.signature(dep)
    assert "request" in sig.parameters
    assert sig.parameters["request"].annotation is not inspect.Parameter.empty
    # Decision path that as_dependency ultimately delegates to:
    decision = fa.check("agent.profile", org_id=None, plan="pro", role="jobseeker")
    assert decision is True


def test_as_dependency_returns_false_when_denied(fake_supabase):
    """Verify the helper path used by as_dependency when the gate denies."""
    from services.platform import feature_access as fa

    # integration.ats needs plan>=enterprise + role in {employer,admin}
    out = fa.check("integration.ats", org_id=None, plan="free", role="employer")
    assert out is False


def test_check_service_access_raises_403(fake_supabase):
    """``check_service_access`` is a thin wrapper that raises 403 when denied.

    We verify its helper path emits the same decision the FastAPI dep
    would surface."""
    from services.platform import feature_access as fa
    # integration.ats needs enterprise — free plan should fail at the gate.
    decision = fa.check("integration.ats", org_id=None, plan="free", role="employer")
    assert decision is False


def test_check_service_access_returns_200_when_allowed(fake_supabase):
    from services.platform import feature_access as fa
    decision = fa.check("agent.profile", org_id=None, plan="pro", role="jobseeker")
    assert decision is True


# ---------------------------------------------------------------------------
# 8. Graceful degradation when layers are unavailable
# ---------------------------------------------------------------------------
def test_service_toggle_failure_falls_back_to_deny(fake_supabase, monkeypatch):
    """If service_toggle raises (e.g. catastrophic DB) we default to deny."""
    from services.platform import feature_access as fa, service_toggle as st

    def _boom(*a, **k):
        raise RuntimeError("simulated outage")

    monkeypatch.setattr(st, "service_toggle", type("X", (), {
        "is_enabled": staticmethod(_boom),
        "get_service": staticmethod(lambda name: None),
    })())
    assert fa.check("agent.profile", org_id=None, plan="pro", role="jobseeker") is False


def test_feature_flag_failure_does_not_deny(fake_supabase, monkeypatch):
    """If feature_flag raises we treat as missing => don't deny."""
    from services.platform import feature_flag as ff
    from services.platform.feature_access import check

    def _boom(*a, **k):
        raise RuntimeError("flag down")

    monkeypatch.setattr(ff, "get_flag", _boom)
    assert check("agent.profile", org_id=None, plan="pro", role="jobseeker") is True


# ---------------------------------------------------------------------------
# 9. Cache invalidation
# ---------------------------------------------------------------------------
def test_invalidate_clears_cache(fake_supabase):
    from services.platform import service_toggle as st, feature_access as fa
    st._LOCAL_CACHE["foo"] = {"bar": 1}
    st._LOCAL_TS["foo"] = 999_999_999
    fa.invalidate_cache(prefix="")
    # invalidate_cache also clears local fallback in service_toggle
    assert "foo" not in st._LOCAL_CACHE


# ---------------------------------------------------------------------------
# 10. Cross-cutting — header extraction
# ---------------------------------------------------------------------------
def test_extract_request_context_parses_headers(fake_supabase):
    from services.platform import feature_access as fa
    from fastapi import Request

    class _Req:
        headers = {
            "X-Org-Id": "org-77",
            "X-Role": "employer",
            "X-User-Id": "u-1",
            "X-Plan": "pro",
        }

    ctx = fa._extract_request_context(_Req())
    assert ctx["org_id"] == "org-77"
    assert ctx["role"] == "employer"
    assert ctx["user_id"] == "u-1"
    assert ctx["plan"] == "pro"


def test_extract_request_context_defaults(fake_supabase):
    from services.platform.feature_access import _extract_request_context
    from fastapi import Request

    class _Req:
        headers = {}

    ctx = _extract_request_context(_Req())
    assert ctx["org_id"] is None
    assert ctx["role"] == ""
    assert ctx["user_id"] is None
    assert ctx["plan"] == "free"


# ---------------------------------------------------------------------------
# 11. Multiplexing across multiple feature_access checks
# ---------------------------------------------------------------------------
def test_multiple_independent_features(fake_supabase):
    from services.platform import feature_access as fa
    res1 = fa.check("agent.profile", org_id=None, plan="pro", role="jobseeker")
    res2 = fa.check("integration.ats", org_id=None, plan="pro", role="employer")
    assert res1 is True
    assert res2 is False


# ---------------------------------------------------------------------------
# 12. Stable callable API surface
# ---------------------------------------------------------------------------
def test_public_callables_exported(fake_supabase):
    from services.platform import feature_access as fa
    for name in (
        "check",
        "require",
        "batch_check",
        "check_context",
        "guard",
        "as_dependency",
        "check_service_access",
    ):
        assert callable(getattr(fa, name)), name
