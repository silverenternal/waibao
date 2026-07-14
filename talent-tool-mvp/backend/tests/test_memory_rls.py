"""T5021 — pgvector + RLS tenant isolation tests.

Uses the in-process ``_RLSMemoryTable`` to prove the RLS policy semantics
(tenant-scoped reads/writes) without a live Postgres. Also exercises the
``PgVectorMemoryBackend`` client contract with a fake Supabase client.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.memory.models import Memory, MemoryType  # noqa: E402
from services.memory.store_pgvector import (  # noqa: E402
    PgVectorError,
    PgVectorMemoryBackend,
    _RLSMemoryTable,
)


TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
USER_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_B = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _mem(tenant, user, content, vec=None):
    return Memory(
        tenant_id=tenant,
        user_id=user,
        content=content,
        source_agent="test",
        type=MemoryType.FACT,
        confidence=0.9,
        embedding=vec or [0.1, 0.2, 0.3],
    )


# ---------------------------------------------------------------------------
# In-process RLS simulator
# ---------------------------------------------------------------------------

def test_rls_insert_with_wrong_tenant_is_rejected():
    table = _RLSMemoryTable()
    table.set_tenant(TENANT_A)
    with pytest.raises(PgVectorError):
        table.insert(_mem(TENANT_B, USER_A, "leaked"))


def test_rls_tenant_cannot_read_other_tenant_rows():
    table = _RLSMemoryTable()
    table.set_tenant(TENANT_A)
    table.insert(_mem(TENANT_A, USER_A, "tenant a secret"))
    table.set_tenant(TENANT_B)
    table.insert(_mem(TENANT_B, USER_B, "tenant b secret"))

    # Tenant A lists its user's memories — must NOT see tenant B's row
    a_rows = table.list_for_user(USER_A, tenant_id=TENANT_A)
    assert len(a_rows) == 1
    assert "tenant a" in a_rows[0].content

    # Tenant B queries for USER_A — should get nothing (cross-tenant)
    cross = table.list_for_user(USER_A, tenant_id=TENANT_B)
    assert cross == []


def test_rls_vector_search_is_tenant_scoped():
    table = _RLSMemoryTable()
    table.set_tenant(TENANT_A)
    table.insert(_mem(TENANT_A, USER_A, "shared keyword alpha", vec=[1.0, 0.0]))
    table.set_tenant(TENANT_B)
    table.insert(_mem(TENANT_B, USER_B, "shared keyword alpha", vec=[1.0, 0.0]))

    hits_a = table.search(tenant_id=TENANT_A, user_id=USER_A, query_vec=[1.0, 0.0])
    hits_b = table.search(tenant_id=TENANT_B, user_id=USER_B, query_vec=[1.0, 0.0])
    assert len(hits_a) == 1 and "alpha" in hits_a[0][0].content
    assert len(hits_b) == 1 and "alpha" in hits_b[0][0].content
    # cross-tenant search returns nothing
    cross = table.search(tenant_id=TENANT_A, user_id=USER_B, query_vec=[1.0, 0.0])
    assert cross == []


def test_rls_forget_only_affects_own_tenant():
    table = _RLSMemoryTable()
    table.set_tenant(TENANT_A)
    table.insert(_mem(TENANT_A, USER_A, "a1"))
    table.insert(_mem(TENANT_A, USER_A, "a2"))
    table.set_tenant(TENANT_B)
    # tenant B tries to forget USER_A — must affect 0 rows
    n = table.forget_user(tenant_id=TENANT_B, user_id=USER_A)
    assert n == 0
    # tenant A forgets its own — 2 rows
    n2 = table.forget_user(tenant_id=TENANT_A, user_id=USER_A)
    assert n2 == 2


# ---------------------------------------------------------------------------
# PgVectorMemoryBackend against a fake Supabase client
# ---------------------------------------------------------------------------

class _Resp:
    def __init__(self, data):
        self.data = data


class _Table:
    def __init__(self, store, name):
        self.store = store
        self.name = name
        self._filters: list[tuple[str, str, str]] = []
        self._payload: dict | None = None

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, vals))
        return self

    def limit(self, n):
        return self

    def insert(self, row):
        self._payload = row
        return self

    def update(self, row):
        self._payload = row
        return self

    def delete(self):
        self._payload = {"__delete__": True}
        return self

    def select(self, *_):
        self._payload = {"__select__": True}
        return self

    def execute(self):
        if self._payload and "__select__" in self._payload:
            rows = [r for r in self.store["rows"]]
            for op, col, val in self._filters:
                rows = [r for r in rows if str(r.get(col)) == str(val)]
            self._filters.clear()
            return _Resp(rows)
        if self._payload and "__delete__" in self._payload:
            keep = []
            deleted = []
            for r in self.store["rows"]:
                if all(str(r.get(c)) == str(v) for _, c, v in self._filters):
                    deleted.append(r)
                else:
                    keep.append(r)
            self.store["rows"] = keep
            self._filters.clear()
            return _Resp(deleted)
        if self._payload is not None:
            row = dict(self._payload)
            if isinstance(row.get("embedding"), str):
                row["embedding"] = json.loads(row["embedding"])
            self.store["rows"].append(row)
            self._payload = None
            return _Resp([row])
        return _Resp(None)


class _Rpc:
    def __init__(self, store, name, params):
        self.store = store
        self.name = name
        self.params = params

    def execute(self):
        if self.name == "set_tenant_context":
            self.store["tenant"] = self.params.get("tenant_id")
            return _Resp([])
        if self.name == "match_memories":
            tenant = self.params.get("filter_tenant_id")
            user = self.params.get("filter_user_id")
            q = json.loads(self.params["query_embedding"])
            scored = []
            for r in self.store["rows"]:
                if str(r.get("tenant_id")) != str(tenant):
                    continue
                if str(r.get("user_id")) != str(user):
                    continue
                emb = r.get("embedding") or []
                dot = sum(a * b for a, b in zip(q, emb))
                scored.append({**r, "similarity": dot})
            scored.sort(key=lambda x: x["similarity"], reverse=True)
            return _Resp(scored[: self.params.get("match_count", 10)])
        return _Resp([])


class FakeSupabase:
    def __init__(self):
        self.store = {"rows": [], "tenant": None}

    def table(self, name):
        return _Table(self.store, name)

    def rpc(self, name, params):
        return _Rpc(self.store, name, params)


def test_pgvector_backend_insert_and_get():
    fake = FakeSupabase()
    backend = PgVectorMemoryBackend(
        client_factory=lambda: fake,
        embedder=lambda t: [0.5, 0.5],
    )
    mem = _mem(TENANT_A, USER_A, "real vector memory")
    inserted = backend.insert(mem)
    assert inserted.tenant_id == TENANT_A
    got = backend.get(inserted.id)
    assert got is not None
    assert got.content == "real vector memory"


def test_pgvector_backend_search_uses_rpc_and_is_tenant_scoped():
    fake = FakeSupabase()
    backend = PgVectorMemoryBackend(
        client_factory=lambda: fake,
        embedder=lambda t: [1.0, 0.0],
    )
    backend.insert(_mem(TENANT_A, USER_A, "a-vector", vec=[1.0, 0.0]))
    backend.insert(_mem(TENANT_B, USER_B, "b-vector", vec=[1.0, 0.0]))

    results = backend.search(
        tenant_id=TENANT_A, user_id=USER_A, query_text="q",
    )
    assert len(results) == 1
    assert results[0][0].tenant_id == TENANT_A


def test_pgvector_backend_forget_user():
    fake = FakeSupabase()
    backend = PgVectorMemoryBackend(
        client_factory=lambda: fake,
        embedder=lambda t: [0.1],
    )
    backend.insert(_mem(TENANT_A, USER_A, "m1"))
    backend.insert(_mem(TENANT_A, USER_A, "m2"))
    n = backend.forget_user(tenant_id=TENANT_A, user_id=USER_A)
    assert n == 2


def test_pgvector_backend_raises_without_client():
    def boom():
        raise RuntimeError("no db")
    backend = PgVectorMemoryBackend(client_factory=boom, embedder=lambda t: [0.1])
    with pytest.raises(PgVectorError):
        backend.insert(_mem(TENANT_A, USER_A, "x"))


def test_pgvector_backend_raises_without_embedder():
    fake = FakeSupabase()
    backend = PgVectorMemoryBackend(client_factory=lambda: fake, embedder=None)
    mem = Memory(tenant_id=TENANT_A, user_id=USER_A, content="no embed",
                 source_agent="t", type=MemoryType.FACT, embedding=None)
    with pytest.raises(PgVectorError):
        backend.insert(mem)
