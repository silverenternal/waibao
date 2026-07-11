"""T804 - Rules CRUD + test endpoint 测试."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.rules import router as rules_router
from api.auth import CurrentUser
from contracts.shared import UserRole


# ---------------------------------------------------------------------------
# Mock Supabase
# ---------------------------------------------------------------------------


class _FakeQuery:
    def __init__(self, tables, name, single=False):
        self._tables = tables
        self._table = name
        self._filters = []
        self._limit = None
        self._single = single

    def select(self, *_a, **_kw):
        return self

    def eq(self, k, v):
        self._filters.append(("eq", k, v))
        return self

    def is_(self, k, v):
        self._filters.append(("is", k, v))
        return self

    def order(self, *_a, **_kw):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        rows = list(self._tables.get(self._table, []))
        for op, k, v in self._filters:
            if op == "eq":
                rows = [r for r in rows if str(r.get(k)) == str(v)]
            elif op == "is":
                if v == "null":
                    rows = [r for r in rows if r.get(k) is None]
        if self._limit:
            rows = rows[: self._limit]
        if self._single:
            return SimpleNamespace(data=rows[0] if rows else None)
        return SimpleNamespace(data=rows)


class _FakeSB:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {
            "rules": [],
            "rule_runs": [],
            "users": [
                {
                    "id": "00000000-0000-0000-0000-000000000001",
                    "organisation_id": "org-1",
                },
            ],
        }

    def table(self, name):
        outer = self

        class _Facade:
            def __init__(self):
                self._q = _FakeQuery(outer.tables, name)

            def select(self, *a, **kw):
                return self._q.select(*a, **kw)

            def eq(self, *a, **kw):
                return self._q.eq(*a, **kw)

            def is_(self, *a, **kw):
                return self._q.is_(*a, **kw)

            def order(self, *a, **kw):
                return self._q.order(*a, **kw)

            def limit(self, *a, **kw):
                return self._q.limit(*a, **kw)

            def single(self):
                return self._q.single()

            def insert(self, row):
                outer.tables.setdefault(name, []).append(row)
                return SimpleNamespace(execute=lambda: SimpleNamespace(data=[row]))

            def update(self, patch):
                return SimpleNamespace(
                    eq=lambda *a, **kw: SimpleNamespace(
                        execute=lambda: SimpleNamespace(data=[patch])
                    )
                )

            def upsert(self, *a, **kw):
                return SimpleNamespace(execute=lambda: SimpleNamespace(data=[]))

            def delete(self):
                return SimpleNamespace(
                    eq=lambda *a, **kw: SimpleNamespace(
                        execute=lambda: SimpleNamespace(data=[{"id": "x"}])
                    )
                )

            def execute(self):
                return self._q.execute()

        return _Facade()


@pytest.fixture
def fake_sb():
    return _FakeSB()


def _override_user():
    return CurrentUser(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        email="admin@x.com",
        role=UserRole.admin,
    )


@pytest.fixture
def client(fake_sb):
    app = FastAPI()
    app.include_router(rules_router)
    from api import deps

    deps._supabase_admin_client = fake_sb  # type: ignore[attr-defined]

    from api.auth import get_current_user

    # 简化: 仅 override get_current_user;require_role 内部会调用它.
    app.dependency_overrides[get_current_user] = lambda: _override_user()
    yield TestClient(app)
    deps._supabase_admin_client = None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_create_rule(client):
    body = {
        "name": "low autoresolve",
        "trigger": "HR_SERVICE_AUTORESOLVE_RATE_LOW",
        "condition": {
            "op": "AND",
            "children": [
                {"op": "<", "field": "rate", "value": 0.6},
                {"op": "in", "field": "window", "value": ["7d", "30d"]},
            ],
        },
        "actions": [
            {"type": "notify", "params": {"channel": "email"}},
            {"type": "create_ticket", "params": {"priority": "P1"}},
        ],
        "enabled": True,
    }
    r = client.post("/api/rules", json=body)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["name"] == "low autoresolve"
    assert out["trigger"] == "HR_SERVICE_AUTORESOLVE_RATE_LOW"


def test_create_rule_depth_limit_returns_400(client):
    body = {
        "name": "deep",
        "trigger": "T",
        "condition": {
            "op": "AND",
            "children": [
                {
                    "op": "AND",
                    "children": [
                        {
                            "op": "AND",
                            "children": [
                                {
                                    "op": "AND",
                                    "children": [
                                        {"op": "<", "field": "x", "value": 1}
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        "actions": [],
    }
    r = client.post("/api/rules", json=body)
    assert r.status_code == 400
    assert "嵌套" in r.json()["detail"]


def test_create_rule_invalid_action_type_returns_422(client):
    body = {
        "name": "x",
        "trigger": "T",
        "actions": [{"type": "hacker"}],
    }
    r = client.post("/api/rules", json=body)
    # pydantic validation 422 OR our 400
    assert r.status_code in (400, 422)


def test_test_rule_endpoint(client):
    body = {
        "name": "r",
        "trigger": "T",
        "condition": {"op": "<", "field": "rate", "value": 0.6},
        "actions": [{"type": "emit_event", "params": {"event": "ping"}}],
        "enabled": True,
    }
    create = client.post("/api/rules", json=body)
    rule_id = create.json()["id"]
    r = client.post(
        f"/api/rules/{rule_id}/test",
        json={"context": {"rate": 0.5}, "dry_run": True},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["matched"] is True
    assert out["actions_executed"]


def test_test_rule_no_match(client):
    body = {
        "name": "r",
        "trigger": "T",
        "condition": {"op": ">", "field": "rate", "value": 0.9},
        "actions": [{"type": "emit_event", "params": {"event": "ping"}}],
    }
    create = client.post("/api/rules", json=body)
    rid = create.json()["id"]
    r = client.post(
        f"/api/rules/{rid}/test",
        json={"context": {"rate": 0.1}},
    )
    assert r.json()["matched"] is False


def test_list_triggers_catalogue(client):
    r = client.get("/api/rules/triggers/catalogue")
    assert r.status_code == 200
    data = r.json()
    names = [t["name"] for t in data["triggers"]]
    assert "HR_SERVICE_AUTORESOLVE_RATE_LOW" in names
    assert "MATCH_FUNNEL_DROP" in names


def test_rule_run_history(client):
    body = {
        "name": "r",
        "trigger": "T",
        "condition": {"op": "<", "field": "x", "value": 1},
        "actions": [],
    }
    rid = client.post("/api/rules", json=body).json()["id"]
    r = client.get(f"/api/rules/{rid}/runs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
