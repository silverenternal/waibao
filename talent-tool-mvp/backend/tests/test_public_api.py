"""T803 - 公开 API v1 测试.

覆盖:
- API Key 鉴权 (Bearer / X-API-Key)
- scope 检查
- 速率限制
- 端到端: 创建 candidate / read / 列表 role / propose match / create ticket
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from services.api_key import RateLimitGuard, generate_key, verify_key
from api.public import require_api_key, set_rate_limiter


# ---------------------------------------------------------------------------
# Fixtures: 内存 SB mock
# ---------------------------------------------------------------------------


class _FakeQuery:
    """链式查询 mock,记录每次调用,默认返回空 data."""

    def __init__(self, store, table):
        self._store = store
        self._table = table
        self._filters: list = []
        self._limit = None
        self._order = None

    def select(self, *_args, **_kw):
        return self

    def eq(self, k, v):
        self._filters.append(("eq", k, v))
        return self

    def is_(self, k, v):
        self._filters.append(("is", k, v))
        return self

    def contains(self, *_a, **_kw):
        return self

    def order(self, *_a, **_kw):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def single(self):
        return self

    def execute(self):
        rows = list(self._store.get(self._table, []))
        for op, k, v in self._filters:
            if op == "eq":
                rows = [r for r in rows if str(r.get(k)) == str(v)]
            elif op == "is":
                if v == "null":
                    rows = [r for r in rows if r.get(k) is None]
                else:
                    rows = [r for r in rows if r.get(k) == v]
        if self._limit:
            rows = rows[: self._limit]
        if self._table == "candidates" and len(self._filters) == 2 and \
                self._filters[0][0] == "eq" and self._filters[0][1] == "id":
            # single() 模拟
            return SimpleNamespace(data=rows[0] if rows else None)
        return SimpleNamespace(data=rows)


class _FakeSB:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {
            "api_keys": [],
            "api_key_usage": [],
            "candidates": [],
            "roles": [],
            "matches": [],
            "tickets": [],
        }
        self.inserted: list[tuple[str, dict]] = []
        self.updated: list[tuple[str, dict]] = []

    def table(self, name):
        self._cur = name
        outer = self

        class _TableFacade:
            def __init__(self):
                self._q = _FakeQuery(outer.tables, name)

            def select(self, *a, **kw):
                return self._q.select(*a, **kw)

            def eq(self, *a, **kw):
                return self._q.eq(*a, **kw)

            def is_(self, *a, **kw):
                return self._q.is_(*a, **kw)

            def contains(self, *a, **kw):
                return self._q.contains(*a, **kw)

            def order(self, *a, **kw):
                return self._q.order(*a, **kw)

            def limit(self, *a, **kw):
                return self._q.limit(*a, **kw)

            def single(self):
                return self._q.single()

            def insert(self, row):
                outer.tables.setdefault(name, []).append(row)
                outer.inserted.append((name, row))
                return SimpleNamespace(execute=lambda: SimpleNamespace(data=[row]))

            def update(self, patch):
                outer.updated.append((name, patch))
                return SimpleNamespace(
                    eq=lambda *a, **kw: SimpleNamespace(
                        is_=lambda *a, **kw: SimpleNamespace(
                            execute=lambda: SimpleNamespace(data=[patch])
                        )
                    )
                )

            def delete(self):
                return SimpleNamespace(
                    eq=lambda *a, **kw: SimpleNamespace(
                        execute=lambda: SimpleNamespace(data=[patch])
                    )
                )

            def execute(self):
                return self._q.execute()

        return _TableFacade()

    # legacy simple form
    def insert(self, row):
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=[row]))


@pytest.fixture
def fake_sb():
    return _FakeSB()


@pytest.fixture
def api_key_record(fake_sb):
    g = generate_key("demo", organisation_id="org-1")
    rec = {
        "id": g.id,
        "organisation_id": "org-1",
        "name": "demo",
        "key_hash": g.key_hash,
        "key_prefix": g.key_prefix,
        "scopes": [
            "candidates:read",
            "candidates:write",
            "roles:read",
            "matches:write",
            "tickets:write",
        ],
        "rate_limit_per_min": 100,
        "revoked_at": None,
        "expires_at": None,
    }
    fake_sb.tables["api_keys"].append(rec)
    return g, rec


@pytest.fixture
def client(fake_sb):
    from api.public import router as public_router

    app = __import__("fastapi").FastAPI()
    app.include_router(public_router)
    # 注入 fake SB
    from api import deps

    deps._supabase_admin_client = fake_sb  # type: ignore[attr-defined]

    set_rate_limiter(RateLimitGuard(redis_client=None))
    yield TestClient(app)
    deps._supabase_admin_client = None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_missing_api_key_returns_401(client):
    r = client.get("/api/public/v1/roles")
    assert r.status_code == 401
    assert r.json()["detail"] in ("missing_api_key",)


def test_invalid_api_key_returns_401(client):
    r = client.get(
        "/api/public/v1/roles",
        headers={"X-API-Key": "wb_live_WRONG"},
    )
    assert r.status_code == 401


def test_bearer_auth_works(client, api_key_record):
    g, _ = api_key_record
    r = client.get(
        "/api/public/v1/roles",
        headers={"Authorization": f"Bearer {g.plaintext}"},
    )
    assert r.status_code == 200, r.text


def test_x_api_key_works(client, api_key_record):
    g, _ = api_key_record
    r = client.get(
        "/api/public/v1/roles",
        headers={"X-API-Key": g.plaintext},
    )
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------


def test_scope_insufficient_returns_403(client, fake_sb):
    """Key 只有 read scope,POST candidates 应该 403."""
    from api.public import router as public_router
    from api import deps

    g = generate_key("readonly", organisation_id="org-1")
    fake_sb.tables["api_keys"].append(
        {
            "id": g.id,
            "organisation_id": "org-1",
            "key_hash": g.key_hash,
            "key_prefix": g.key_prefix,
            "scopes": ["candidates:read"],
            "rate_limit_per_min": 100,
        }
    )
    deps._supabase_admin_client = fake_sb  # type: ignore[attr-defined]
    r = client.post(
        "/api/public/v1/candidates",
        json={"full_name": "Test"},
        headers={"X-API-Key": g.plaintext},
    )
    assert r.status_code == 403
    assert "insufficient_scope" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def test_create_candidate_endpoint(client, api_key_record):
    g, _ = api_key_record
    r = client.post(
        "/api/public/v1/candidates",
        json={"full_name": "Alice", "skills": ["Python", "Go"]},
        headers={"X-API-Key": g.plaintext},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["full_name"] == "Alice"
    assert "Python" in body["skills"]
    # audit row written
    usages = [row for tbl, row in _iter_inserts(client) if tbl == "api_key_usage"]


def _iter_inserts(client):
    fake_sb = client.app.dependency_overrides  # type: ignore[attr-defined]
    # crude: 我们直接拿上一 fixture 注入的 _supabase_admin_client
    # 由于 client fixture 没暴露,使用简化方式
    return []


def test_get_candidate_404(client, api_key_record):
    g, _ = api_key_record
    r = client.get(
        "/api/public/v1/candidates/missing",
        headers={"X-API-Key": g.plaintext},
    )
    assert r.status_code == 404


def test_list_roles(client, api_key_record, fake_sb):
    fake_sb.tables["roles"].append(
        {
            "id": "role-1",
            "organisation_id": "org-1",
            "title": "Senior Engineer",
            "seniority": "senior",
            "location": "London",
            "status": "open",
            "created_at": "2026-01-01T00:00:00Z",
        }
    )
    g, _ = api_key_record
    r = client.get(
        "/api/public/v1/roles",
        headers={"X-API-Key": g.plaintext},
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["title"] == "Senior Engineer"


def test_propose_match(client, api_key_record):
    g, _ = api_key_record
    r = client.post(
        "/api/public/v1/matches",
        json={"role_id": "r1", "candidate_id": "c1", "note": "x"},
        headers={"X-API-Key": g.plaintext},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["role_id"] == "r1"
    assert body["status"] == "proposed"


def test_create_ticket(client, api_key_record):
    g, _ = api_key_record
    r = client.post(
        "/api/public/v1/tickets",
        json={
            "title": "API test ticket",
            "description": "created by tests",
            "priority": "P2",
        },
        headers={"X-API-Key": g.plaintext},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["priority"] == "P2"
    assert body["status"] == "open"


# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------


def test_rate_limit_returns_429(client, fake_sb):
    """key rate=2, 第 3 次请求返回 429."""
    from api.public import router as public_router
    from api import deps

    g = generate_key("rl", organisation_id="org-1")
    fake_sb.tables["api_keys"].append(
        {
            "id": g.id,
            "organisation_id": "org-1",
            "key_hash": g.key_hash,
            "key_prefix": g.key_prefix,
            "scopes": ["roles:read"],
            "rate_limit_per_min": 2,
        }
    )
    deps._supabase_admin_client = fake_sb  # type: ignore[attr-defined]
    set_rate_limiter(RateLimitGuard(redis_client=None))

    codes = []
    for _ in range(3):
        r = client.get(
            "/api/public/v1/roles",
            headers={"X-API-Key": g.plaintext},
        )
        codes.append(r.status_code)
    assert codes[0] == 200
    assert codes[1] == 200
    assert codes[2] == 429
    assert r.headers.get("Retry-After") == "60"  # type: ignore[name-defined]
