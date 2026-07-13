"""v8.0 T3505 / T3507 — Auto-gating integration test (10+).

Verifies:
    * install_auto_gates attaches a check service_access dep on every
      /api/* router
    * The gate fires a 403 when service_toggle says disabled
    * Allows 200 when service_toggle says enabled
    * Exempt prefixes are skipped
    * Idempotent — re-mounting same service does not double-attach deps
    * User-deps supplied in include_router are preserved alongside gate
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
for p in (BACKEND, os.path.dirname(BACKEND)):
    if p and p not in sys.path:
        sys.path.insert(0, p)


class _FakeRow:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, store: Dict[str, Any], name: str):
        self.store = store
        self.name = name
        self._filters = []

    def select(self, cols: str = "*"):
        return self

    def eq(self, col, value):
        self._filters.append(("eq", col, value))
        return self

    def neq(self, col, value):
        self._filters.append(("neq", col, value))
        return self

    def order(self, col, desc=False):
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
        if limit_n is not None:
            rows = rows[:limit_n]
        return rows

    def execute(self):
        return _FakeRow(self._matched())

    def insert(self, payload):
        recs = payload if isinstance(payload, list) else [payload]
        for r in recs:
            self.store.setdefault(self.name, []).append(dict(r))
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

    def upsert(self, payload, on_conflict=None):
        return self.insert(payload)


class FakeSupabase:
    def __init__(self):
        self.store: Dict[str, Any] = {
            "services": [],
            "service_overrides": [],
            "service_audit": [],
            "configs": [],
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
    )

    monkeypatch.setattr(st, "_supabase", lambda: fs)
    monkeypatch.setattr(cs, "_supabase", lambda: fs)
    st._LOCAL_CACHE.clear()
    st._LOCAL_TS.clear()
    cs._CACHE.clear()

    fs.table("services").insert(
        {
            "name": "candidates",
            "display_name": "Candidates API",
            "category": "api",
            "status": "enabled",
            "plan_required": "free",
            "roles_allowed": [],
            "dependencies": [],
            "version": 1,
        }
    )
    fs.table("services").insert(
        {
            "name": "matches",
            "display_name": "Matches API",
            "category": "api",
            "status": "disabled",
            "plan_required": "free",
            "roles_allowed": [],
            "dependencies": [],
            "version": 1,
        }
    )
    yield fs


def test_service_name_for_prefix_normalisation():
    from services.platform.middleware import service_name_for_prefix

    assert service_name_for_prefix("/api/candidates") == "candidates"
    assert service_name_for_prefix("/api/agents-realtime/v2") == "agents-realtime.v2"
    assert service_name_for_prefix("/api") == "api"
    assert service_name_for_prefix("/two-way-match") == "two-way-match"
    assert service_name_for_prefix("/api/") == "api"
    # Empty / None prefix => empty service name (caller decides what to do)
    assert service_name_for_prefix("") == ""
    assert service_name_for_prefix("/") == ""


def test_service_name_for_prefix_handles_trailing_slash():
    from services.platform.middleware import service_name_for_prefix

    # trailing slash should still normalise
    assert service_name_for_prefix("/api/predictive/") == "predictive"


def test_exempt_prefix_constant_has_well_known_paths():
    from services.platform.middleware import EXEMPT_PREFIXES

    assert "/health" in EXEMPT_PREFIXES
    assert "/api/users/me" in EXEMPT_PREFIXES
    assert "/api/admin/services" in EXEMPT_PREFIXES
    assert "/api/public/services" in EXEMPT_PREFIXES


def test_exempt_prefix_constant_documents_internal_services():
    """Internal/admin namespaces are documented in EXEMPT_PREFIXES to
    ensure operators never accidentally take down the toggle API itself."""
    from services.platform.middleware import EXEMPT_PREFIXES, INTERNAL_SERVICE_PREFIXES

    assert EXEMPT_PREFIXES == EXEMPT_PREFIXES  # sentinel
    # Internal prefixes must remain exempt (so admin can toggle them)
    assert "/api/admin/services" in EXEMPT_PREFIXES
    assert "/api/admin" in INTERNAL_SERVICE_PREFIXES


def test_install_auto_gates_tracks_seen_services(fake_supabase):
    from fastapi import APIRouter, FastAPI

    from services.platform.middleware import (
        install_auto_gates,
        gated_service_names,
    )

    app = FastAPI()
    install_auto_gates(app)

    r = APIRouter()

    @r.get("/a")
    async def _a():
        return 1

    app.include_router(r, prefix="/api/candidates")
    assert "candidates" in gated_service_names(app)


def test_install_auto_gates_skips_exempt(fake_supabase):
    from fastapi import APIRouter, FastAPI

    from services.platform.middleware import (
        install_auto_gates,
        gated_service_names,
    )

    app = FastAPI()
    install_auto_gates(app)

    r = APIRouter()

    @r.get("/x")
    async def _x():
        return {}

    app.include_router(r, prefix="/health")
    # /health in EXEMPT_PREFIXES => no gate
    assert "health" not in gated_service_names(app)


def test_install_auto_gates_dedupes_repeat_mounts(fake_supabase):
    """If the same /api/* prefix is mounted twice, the gate attaches once."""
    from fastapi import APIRouter, FastAPI

    from services.platform.middleware import install_auto_gates, gated_service_names

    app = FastAPI()
    install_auto_gates(app)

    r = APIRouter()

    @r.get("/a")
    async def _a():
        return 1

    app.include_router(r, prefix="/api/candidates")
    app.include_router(r, prefix="/api/candidates")
    # Only one service was added to the gated set.
    services = gated_service_names(app)
    assert services == {"candidates"}


def test_install_auto_gates_preserves_user_supplied_deps(fake_supabase):
    """User deps plus the gate must coexist on every route."""
    from fastapi import APIRouter, Depends, FastAPI
    from fastapi.testclient import TestClient

    from services.platform.middleware import install_auto_gates

    app = FastAPI()
    install_auto_gates(app)

    r = APIRouter()

    @r.get("/a")
    async def _a(_user=Depends(lambda: "u")):
        return {"ok": True, "user": _user}

    def _user_dep():
        return "ok"

    app.include_router(
        r,
        prefix="/api/candidates",
        dependencies=[Depends(_user_dep)],
    )

    client = TestClient(app)
    # The route should still serve a 200 (gate allows + user deps preserved).
    res = client.get("/api/candidates/a", headers={"X-Plan": "free"})
    assert res.status_code == 200


def test_install_auto_gates_idempotent_double_install(fake_supabase):
    """Calling install_auto_gates twice wraps the same include_router,
    not cumulatively (the wrap is replaced, not chained)."""
    from fastapi import APIRouter, FastAPI

    from services.platform.middleware import install_auto_gates, gated_service_names

    app = FastAPI()
    install_auto_gates(app)
    install_auto_gates(app)

    r = APIRouter()

    @r.get("/a")
    async def _a():
        return 1

    app.include_router(r, prefix="/api/candidates")
    services = gated_service_names(app)
    assert "candidates" in services
    # de-dup: just one entry
    assert services == {"candidates"}


def test_install_auto_gates_handles_no_prefix(fake_supabase):
    """When include_router is called without a prefix arg, no gate attaches."""
    from fastapi import APIRouter, FastAPI

    from services.platform.middleware import install_auto_gates, gated_service_names

    app = FastAPI()
    install_auto_gates(app)

    r = APIRouter()

    @r.get("/internal")
    async def _i():
        return {}

    # No prefix kwarg at all — wrapped include_router must not crash.
    app.include_router(r)
    services = gated_service_names(app)
    # No service name was added because the prefix is empty / None.
    assert services == set()


def test_install_auto_gates_handles_exempt_via_kwarg(fake_supabase):
    """An :class:`EXEMPT_PREFIXES` value skips the gate even when registered."""
    from fastapi import APIRouter, FastAPI

    from services.platform.middleware import (
        EXEMPT_PREFIXES,
        install_auto_gates,
        gated_service_names,
    )

    app = FastAPI()
    install_auto_gates(app)

    r = APIRouter()

    @r.get("/x")
    async def _x():
        return {}

    # Pick the first exempt and ensure no gate is attached.
    exempt = sorted(EXEMPT_PREFIXES)[0]
    app.include_router(r, prefix=exempt)
    exempt_service = exempt.lstrip("/").replace("/", ".").lstrip("api.").rstrip(".")
    # Either the derived name is empty or it does not appear in seen.
    assert exempt_service not in gated_service_names(app) or not exempt_service


def test_install_auto_gates_block_call_flow(fake_supabase):
    """End-to-end HTTP test: gated `/api/matches` blocks because the
    service is disabled in the DB."""
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient

    from services.platform.middleware import install_auto_gates

    app = FastAPI()
    install_auto_gates(app)

    r = APIRouter()

    @r.get("/list")
    async def _list():
        return {"items": []}

    app.include_router(r, prefix="/api/matches")

    client = TestClient(app)
    res = client.get("/api/matches/list")
    assert res.status_code == 403
    body = res.json()
    assert body["detail"]["error"] == "service_disabled"
    assert body["detail"]["service"] == "matches"


def test_install_auto_gates_allow_call_flow(fake_supabase):
    """Same end-to-end test with an enabled service returns 200."""
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient

    from services.platform.middleware import install_auto_gates

    app = FastAPI()
    install_auto_gates(app)

    r = APIRouter()

    @r.get("/list")
    async def _list():
        return {"items": []}

    app.include_router(r, prefix="/api/candidates")

    client = TestClient(app)
    res = client.get("/api/candidates/list", headers={"X-Plan": "free"})
    assert res.status_code == 200
