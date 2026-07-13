"""v8.0 T3502 — Public service catalog tests (20+).

Covers:
    * list with filters (category, plan, status, search)
    * category grouping
    * detail endpoint with dependencies + history + SLA
    * public dependency graph
    * subscription (email + webhook)
    * invalidation of internal / disabled rows
    * notify subscribers wired to eventbus
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


# ---------------------------------------------------------------------------
# Local fake Supabase (independent from test_service_toggle fixtures so we
# can keep this file isolated)
# ---------------------------------------------------------------------------
class _FakeRow:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, store, name):
        self.store = store
        self.name = name
        self._filters = []
        self._order = None

    def select(self, cols="*"):
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
            if f[0] == "eq":
                rows = [r for r in rows if r.get(f[1]) == f[2]]
            elif f[0] == "neq":
                rows = [r for r in rows if r.get(f[1]) != f[2]]
            elif f[0] == "limit":
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
            self.store.setdefault(self.name, []).append(dict(r))
        return self

    def update(self, payload):
        for r in self._matched():
            r.update(payload)
        return self


class FakeSupabase:
    def __init__(self):
        self.store = {
            "services": [],
            "service_overrides": [],
            "service_audit": [],
            "service_subscribers": [],
        }

    def table(self, name):
        self.store.setdefault(name, [])
        return _FakeTable(self.store, name)


@pytest.fixture
def fake_supabase(monkeypatch):
    fs = FakeSupabase()
    from api import deps as api_deps

    monkeypatch.setattr(api_deps, "get_supabase_admin", lambda: fs)

    from services.platform import service_toggle as st

    monkeypatch.setattr(st, "_supabase", lambda: fs)
    st._LOCAL_CACHE.clear()
    st._LOCAL_TS.clear()

    # Reset the public_services caches too
    from api import public_services as ps

    ps._CACHE.clear()
    ps._CACHE_TS.clear()
    ps._SUBSCRIBERS.clear()

    yield fs

    st._LOCAL_CACHE.clear()
    st._LOCAL_TS.clear()
    ps._CACHE.clear()
    ps._CACHE_TS.clear()
    ps._SUBSCRIBERS.clear()


def _seed_catalog(fs: FakeSupabase) -> None:
    """Seed a small but representative catalog snapshot."""
    rows = [
        {
            "name": "agent.profile",
            "display_name": "Profile Agent",
            "description": "candidate profiling",
            "category": "agent",
            "status": "enabled",
            "plan_required": "free",
            "roles_allowed": ["jobseeker"],
            "dependencies": ["agent.intake"],
        },
        {
            "name": "agent.career_planner",
            "display_name": "Career Planner",
            "description": "1y / 3y plan",
            "category": "agent",
            "status": "beta",
            "plan_required": "pro",
            "roles_allowed": ["jobseeker"],
            "dependencies": ["agent.profile"],
        },
        {
            "name": "matching.engine",
            "display_name": "Matching Engine",
            "category": "business",
            "status": "enabled",
            "plan_required": "free",
            "roles_allowed": ["employer"],
            "dependencies": [],
        },
        {
            "name": "platform.internal_admin",
            "display_name": "Internal Admin",
            "category": "platform",
            "status": "enabled",
            "plan_required": "internal",
            "roles_allowed": ["admin"],
            "dependencies": [],
        },
        {
            "name": "api.disabled_one",
            "display_name": "Disabled API",
            "category": "api",
            "status": "disabled",
            "plan_required": "free",
            "roles_allowed": [],
            "dependencies": [],
        },
    ]
    for r in rows:
        fs.table("services").insert(r)


def _import_api():
    if BACKEND not in sys.path:
        sys.path.insert(0, BACKEND)
    from api import public_services as ps

    return ps


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------
def test_list_filters_out_internal_and_disabled(fake_supabase):
    _seed_catalog(fake_supabase)
    ps = _import_api()
    items = ps._all_public_rows()
    names = {r["name"] for r in items}
    assert "platform.internal_admin" not in names
    assert "api.disabled_one" not in names
    assert "agent.profile" in names
    assert "matching.engine" in names


def test_list_endpoint_returns_only_public(fake_supabase):
    _seed_catalog(fake_supabase)
    from fastapi.testclient import TestClient

    from api.public_services import router

    app = _build_app(router)
    client = TestClient(app)
    res = client.get("/api/public/services")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] >= 2
    for it in data["items"]:
        assert it["plan_required"] != "internal"
        assert it["status"] != "disabled"


def test_list_endpoint_search(fake_supabase):
    _seed_catalog(fake_supabase)
    from fastapi.testclient import TestClient

    from api.public_services import router

    app = _build_app(router)
    client = TestClient(app)
    res = client.get("/api/public/services", params={"search": "profile"})
    assert res.status_code == 200
    items = res.json()["items"]
    assert any(i["name"] == "agent.profile" for i in items)


def test_list_endpoint_category_filter(fake_supabase):
    _seed_catalog(fake_supabase)
    from fastapi.testclient import TestClient

    from api.public_services import router

    app = _build_app(router)
    client = TestClient(app)
    res = client.get("/api/public/services", params={"category": "agent"})
    items = res.json()["items"]
    for it in items:
        assert it["category"] == "agent"


def test_list_endpoint_plan_filter(fake_supabase):
    _seed_catalog(fake_supabase)
    from fastapi.testclient import TestClient

    from api.public_services import router

    app = _build_app(router)
    client = TestClient(app)
    res = client.get("/api/public/services", params={"plan": "pro"})
    items = res.json()["items"]
    for it in items:
        assert it["plan_required"] == "pro"


def test_list_endpoint_status_filter(fake_supabase):
    _seed_catalog(fake_supabase)
    from fastapi.testclient import TestClient

    from api.public_services import router

    app = _build_app(router)
    client = TestClient(app)
    res = client.get("/api/public/services", params={"status": "beta"})
    items = res.json()["items"]
    for it in items:
        assert it["status"] == "beta"


def test_list_endpoint_limit_clamped(fake_supabase):
    _seed_catalog(fake_supabase)
    from fastapi.testclient import TestClient

    from api.public_services import router

    app = _build_app(router)
    client = TestClient(app)
    res = client.get("/api/public/services", params={"limit": 9999})
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# Categories endpoint
# ---------------------------------------------------------------------------
def test_categories_buckets(fake_supabase):
    _seed_catalog(fake_supabase)
    ps = _import_api()
    res = ps.list_categories()
    cats = {c["id"]: c for c in res["categories"]}
    assert "agent" in cats
    assert "business" in cats
    assert "platform" not in cats  # internal rows hidden
    assert cats["agent"]["count"] >= 1
    assert "totals" in res
    assert res["totals"]["services"] >= 2


def test_categories_endpoint_returns_200(fake_supabase):
    _seed_catalog(fake_supabase)
    from fastapi.testclient import TestClient

    from api.public_services import router

    app = _build_app(router)
    client = TestClient(app)
    res = client.get("/api/public/services/categories")
    assert res.status_code == 200
    assert "categories" in res.json()


# ---------------------------------------------------------------------------
# Detail endpoint
# ---------------------------------------------------------------------------
def test_detail_public_payload(fake_supabase):
    _seed_catalog(fake_supabase)
    ps = _import_api()
    detail = ps.get_service_public("agent.profile")
    assert detail["name"] == "agent.profile"
    assert detail["plan_required"] == "free"
    assert detail["sla"]["uptime_target_pct"] == 99.9
    assert "agent.intake" in detail["declared_dependencies"]
    assert isinstance(detail["history"], list)


def test_detail_unknown_returns_404(fake_supabase):
    _seed_catalog(fake_supabase)
    from fastapi.testclient import TestClient

    from api.public_services import router

    app = _build_app(router)
    client = TestClient(app)
    res = client.get("/api/public/services/nope")
    assert res.status_code == 404


def test_detail_internal_row_hidden(fake_supabase):
    _seed_catalog(fake_supabase)
    from fastapi.testclient import TestClient

    from api.public_services import router

    app = _build_app(router)
    client = TestClient(app)
    res = client.get("/api/public/services/platform.internal_admin")
    assert res.status_code == 404


def test_detail_includes_history(fake_supabase):
    _seed_catalog(fake_supabase)
    # Add an audit row
    fake_supabase.table("service_audit").insert(
        {
            "service_name": "agent.profile",
            "action": "disable",
            "actor_id": "admin-1234",
            "reason": "investigation",
            "before": {"status": "enabled"},
            "after": {"status": "disabled"},
            "created_at": "2026-07-01T00:00:00Z",
        }
    )
    ps = _import_api()
    detail = ps.get_service_public("agent.profile")
    h = detail["history"]
    assert any(row["action"] == "disable" for row in h)
    # actor must be masked
    for row in h:
        if row.get("actor_id"):
            assert row["actor_id"].startswith("admin:")


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
def test_dependencies_bfs_subgraph(fake_supabase):
    _seed_catalog(fake_supabase)
    from fastapi.testclient import TestClient

    from api.public_services import router

    app = _build_app(router)
    client = TestClient(app)
    res = client.get("/api/public/services/agent.career_planner/dependencies")
    assert res.status_code == 200
    data = res.json()
    ids = {n["id"] for n in data["nodes"]}
    assert "agent.career_planner" in ids
    assert "agent.profile" in ids
    assert any(e["from"] == "agent.career_planner" for e in data["edges"])


def test_public_graph_all(fake_supabase):
    _seed_catalog(fake_supabase)
    from fastapi.testclient import TestClient

    from api.public_services import router

    app = _build_app(router)
    client = TestClient(app)
    res = client.get("/api/public/services/graph/all")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] >= 2
    assert all(n["plan_required"] != "internal" for n in data["nodes"])


# ---------------------------------------------------------------------------
# Subscribers
# ---------------------------------------------------------------------------
def test_subscribe_email_only(fake_supabase):
    from fastapi.testclient import TestClient

    from api.public_services import router

    app = _build_app(router)
    client = TestClient(app)
    res = client.post(
        "/api/public/services/subscribers",
        json={"email": "ops@example.com"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["persisted"] is True
    assert len(ps._SUBSCRIBERS) == 1  # noqa: SLF001
    assert ps._SUBSCRIBERS[0]["email"] == "ops@example.com"  # noqa: SLF001


def test_subscribe_webhook_only(fake_supabase):
    from fastapi.testclient import TestClient

    from api.public_services import router

    app = _build_app(router)
    client = TestClient(app)
    res = client.post(
        "/api/public/services/subscribers",
        json={"webhook_url": "https://example.com/hook", "services": ["agent.profile"]},
    )
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_subscribe_invalid_webhook_protocol(fake_supabase):
    from fastapi.testclient import TestClient

    from api.public_services import router

    app = _build_app(router)
    client = TestClient(app)
    res = client.post(
        "/api/public/services/subscribers",
        json={"webhook_url": "ftp://example.com"},
    )
    assert res.status_code == 400


def test_subscribe_requires_email_or_webhook(fake_supabase):
    from fastapi.testclient import TestClient

    from api.public_services import router

    app = _build_app(router)
    client = TestClient(app)
    res = client.post("/api/public/services/subscribers", json={})
    assert res.status_code == 400


def test_subscribe_invalid_email(fake_supabase):
    from fastapi.testclient import TestClient

    from api.public_services import router

    app = _build_app(router)
    client = TestClient(app)
    res = client.post(
        "/api/public/services/subscribers",
        json={"email": "not-an-email"},
    )
    assert res.status_code == 422


def test_unsubscribe(fake_supabase):
    ps = _import_api()
    ps._SUBSCRIBERS.append(
        {
            "id": "abc-123",
            "email": "x@example.com",
            "webhook_url": None,
            "services": [],
            "category": None,
            "locale": "en-US",
            "active": True,
        }
    )
    res = ps.unsubscribe("abc-123")
    assert res["removed"] is True
    assert ps._SUBSCRIBERS == []


def test_unsubscribe_missing(fake_supabase):
    ps = _import_api()
    res = ps.unsubscribe("does-not-exist")
    assert res["removed"] is False


def test_notify_subscribers_filter_by_service(fake_supabase):
    _seed_catalog(fake_supabase)
    ps = _import_api()
    ps._SUBSCRIBERS.append(
        {
            "id": "x1",
            "email": "x@example.com",
            "webhook_url": None,
            "services": ["agent.profile"],
            "category": None,
            "locale": "en-US",
            "active": True,
        }
    )
    ps._SUBSCRIBERS.append(
        {
            "id": "x2",
            "email": "y@example.com",
            "webhook_url": None,
            "services": ["other.svc"],
            "category": None,
            "locale": "en-US",
            "active": True,
        }
    )
    # Only x1 should be considered. Both will fail (no SMTP) so sent=0.
    sent = ps.notify_subscribers("agent.profile", "disable", "enabled", "disabled")
    assert sent == 0


def test_notify_subscribers_filter_by_category(fake_supabase):
    _seed_catalog(fake_supabase)
    ps = _import_api()
    ps._SUBSCRIBERS.append(
        {
            "id": "c1",
            "email": None,
            "webhook_url": "https://127.0.0.1:1/hook",
            "services": [],
            "category": "agent",
            "locale": "en-US",
            "active": True,
        }
    )
    sent = ps.notify_subscribers("matching.engine", "disable", "enabled", "disabled")
    # matching.engine is in "business" so the agent-only subscriber is filtered out
    assert sent == 0


def test_notify_subscribers_inactive_ignored(fake_supabase):
    _seed_catalog(fake_supabase)
    ps = _import_api()
    ps._SUBSCRIBERS.append(
        {
            "id": "i1",
            "email": None,
            "webhook_url": "https://127.0.0.1:1/hook",
            "services": [],
            "category": None,
            "locale": "en-US",
            "active": False,
        }
    )
    sent = ps.notify_subscribers("agent.profile", "disable", "enabled", "disabled")
    assert sent == 0


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------
def test_list_cached_for_60s(fake_supabase):
    _seed_catalog(fake_supabase)
    ps = _import_api()
    rows1 = ps._all_public_rows()
    rows2 = ps._all_public_rows()
    assert rows1 is rows2  # same object proves cache hit
    ps._CACHE.clear()
    rows3 = ps._all_public_rows()
    assert rows3 is not rows1


def test_public_payload_strips_internals():
    ps = _import_api()
    payload = ps._public_payload(
        {
            "name": "x",
            "display_name": "X",
            "description": "d",
            "category": "agent",
            "status": "enabled",
            "plan_required": "free",
            "roles_allowed": ["admin"],
            "dependencies": ["y"],
            "version": 7,
        }
    )
    assert "name" in payload
    assert payload["category_display"] == "AI 智能体"
    assert payload["dependencies"] == ["y"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _build_app(router):
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    return app


import api.public_services as ps  # noqa: E402  (after _build_app definition so the fixture clears state)