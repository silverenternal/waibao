"""T2702 — Agent 统一记忆库测试.

覆盖:
  * Memory data model 序列化 / 反序列化
  * InMemoryBackend CRUD / search / decay / touch / access log
  * MemoryStore 高层 API:add / query / link / decay / forget
  * 跨 agent 记忆共享 (一个 agent 写入,另一个 agent 读出)
  * GDPR 撤回 (forget by predicate)
  * EntityExtractor 启发式抽取
  * MemoryInjector context 块生成
  * EventBus subscribers (profile.updated / preference.expressed / ...)
  * Agent adapter (memory_aware_run)
  * API 端点 (FastAPI app + TestClient)
  * Decay 衰减逻辑 (随时间 decrease + access 时反弹)
  * 重复 / dedup / 多类型
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest

# Ensure backend on path when running from repo root
_BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from services.memory import (
    EntityExtractor,
    Memory,
    MemoryInjector,
    MemoryLink,
    MemoryStore,
    MemoryType,
    RelationType,
    get_memory_store,
    install_memory_subscribers,
    reset_memory_store,
)
from services.memory.extractor import (
    _FACT_PATTERNS,
    _PREFERENCE_PATTERNS,
)
from services.memory.store import (
    InMemoryBackend,
    MemoryStoreError,
    SupabaseBackend,
    _cosine,
    _hash_embed,
    _try_mem0,
)
from services.memory.models import MemoryQuery
from services.memory.agent_adapter import MemoryAwareAgent, memory_aware_run

from eventbus import emit, get_event_bus, reset_event_bus, set_event_bus
from eventbus.base import Event, InMemoryEventBus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_singletons():
    reset_memory_store()
    yield
    reset_memory_store()
    reset_event_bus()


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Data model tests
# ---------------------------------------------------------------------------

class TestMemoryModel:
    def test_default_fields(self):
        m = Memory(
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            content="hello",
            source_agent="test",
        )
        assert m.type == MemoryType.FACT
        assert m.confidence == 1.0
        assert m.decay_score == 1.0
        assert m.access_count == 0
        assert m.is_archived is False
        assert m.metadata == {}

    def test_to_dict_roundtrip(self):
        m = Memory(
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            content="x",
            source_agent="s",
        )
        d = m.to_dict()
        m2 = Memory(**d)
        assert m.content == m2.content
        assert m.type == m2.type

    def test_from_row_with_string_embedding(self):
        row = {
            "id": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "content": "abc",
            "summary": None,
            "embedding": json.dumps([0.1, 0.2, 0.3]),
            "source_agent": "x",
            "type": "preference",
            "confidence": 0.5,
            "decay_score": 0.8,
            "access_count": 3,
            "last_accessed": None,
            "metadata": {"k": 1},
            "is_archived": False,
            "created_at": "2026-07-01T00:00:00",
            "updated_at": "2026-07-02T00:00:00",
        }
        m = Memory.from_row(row)
        assert m.embedding == [0.1, 0.2, 0.3]
        assert m.type == MemoryType.PREFERENCE
        assert m.confidence == 0.5
        assert m.metadata == {"k": 1}


# ---------------------------------------------------------------------------
# Hash embed / cosine
# ---------------------------------------------------------------------------

class TestEmbeddings:
    def test_hash_embed_normalized(self):
        v = _hash_embed("the quick brown fox")
        n = sum(x * x for x in v) ** 0.5
        assert abs(n - 1.0) < 1e-6

    def test_hash_embed_empty(self):
        v = _hash_embed("")
        assert len(v) == 1024
        assert all(x == 0.0 for x in v)

    def test_cosine_identical(self):
        a = _hash_embed("python programming")
        b = _hash_embed("python programming")
        assert _cosine(a, b) > 0.99

    def test_cosine_orthogonal(self):
        a = _hash_embed("apple banana cherry")
        b = _hash_embed("zebra xylophone quantum")
        assert -1.0 <= _cosine(a, b) <= 1.0


class TestMem0Optional:
    def test_try_mem0_is_none_or_class(self):
        # Best-effort import — never raises; returns None if not installed
        c = _try_mem0()
        assert c is None or callable(c)


# ---------------------------------------------------------------------------
# InMemoryBackend
# ---------------------------------------------------------------------------

class TestInMemoryBackend:
    def test_insert_and_get(self):
        b = InMemoryBackend()
        m = Memory(
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            content="x",
            source_agent="s",
        )
        b.insert(m)
        assert b.get(m.id) is not None

    def test_delete_removes_memory_and_links(self):
        b = InMemoryBackend()
        u = uuid.uuid4()
        a = b.insert(Memory(tenant_id=uuid.uuid4(), user_id=u, content="a", source_agent="s"))
        c = b.insert(Memory(tenant_id=uuid.uuid4(), user_id=u, content="c", source_agent="s"))
        b.add_link(MemoryLink(memory_id_a=a.id, memory_id_b=c.id, relation=RelationType.RELATED))
        b.delete(a.id)
        assert b.get(a.id) is None
        assert b.links_for(a.id) == []

    def test_search_ranks_by_similarity(self):
        b = InMemoryBackend()
        u = uuid.uuid4()
        b.insert(Memory(tenant_id=uuid.uuid4(), user_id=u, content="I love Python programming", source_agent="s"))
        b.insert(Memory(tenant_id=uuid.uuid4(), user_id=u, content="salary expectations 200k", source_agent="s"))
        b.insert(Memory(tenant_id=uuid.uuid4(), user_id=u, content="remote work preferred", source_agent="s"))
        scored = b.search(u, "python software engineer", top_k=3)
        assert scored[0][0].content.startswith("I love Python")

    def test_decay_lowers_scores(self):
        b = InMemoryBackend()
        u = uuid.uuid4()
        b.insert(Memory(tenant_id=uuid.uuid4(), user_id=u, content="x", source_agent="s"))
        before = next(iter(b._memories.values())).decay_score
        n = b.decay_all(0.9)
        after = next(iter(b._memories.values())).decay_score
        assert n == 1
        assert after == pytest.approx(before * 0.9)

    def test_touch_increments_and_raises_decay(self):
        b = InMemoryBackend()
        u = uuid.uuid4()
        m = b.insert(Memory(tenant_id=uuid.uuid4(), user_id=u, content="x", source_agent="s", decay_score=0.5))
        b.touch(m.id)
        m2 = b.get(m.id)
        assert m2.access_count == 1
        assert m2.decay_score >= 0.5

    def test_list_filters_by_type_and_user(self):
        b = InMemoryBackend()
        u1, u2 = uuid.uuid4(), uuid.uuid4()
        b.insert(Memory(tenant_id=uuid.uuid4(), user_id=u1, content="a", source_agent="s", type=MemoryType.FACT))
        b.insert(Memory(tenant_id=uuid.uuid4(), user_id=u1, content="b", source_agent="s", type=MemoryType.PREFERENCE))
        b.insert(Memory(tenant_id=uuid.uuid4(), user_id=u2, content="c", source_agent="s"))
        out = b.list_for_user(u1, types=[MemoryType.PREFERENCE])
        assert len(out) == 1
        assert out[0].content == "b"

    def test_access_log(self):
        b = InMemoryBackend()
        u = uuid.uuid4()
        m = b.insert(Memory(tenant_id=uuid.uuid4(), user_id=u, content="x", source_agent="s"))
        b.log_access(memory_id=m.id, user_id=u, action="write", actor_kind="agent")
        b.log_access(memory_id=m.id, user_id=u, action="read", actor_kind="user")
        log = b.access_log(u)
        assert len(log) == 2
        assert {e["action"] for e in log} == {"write", "read"}


# ---------------------------------------------------------------------------
# MemoryStore high-level
# ---------------------------------------------------------------------------

class TestMemoryStore:
    def test_add_returns_memory(self, store, user_id, tenant_id):
        m = store.add(
            user_id=user_id,
            content="user likes remote work",
            source_agent="profile_agent",
            type=MemoryType.PREFERENCE,
            tenant_id=tenant_id,
        )
        assert m.id is not None
        assert m.user_id == user_id
        assert m.source_agent == "profile_agent"
        assert m.type == MemoryType.PREFERENCE

    def test_query_returns_relevant(self, store, user_id, tenant_id):
        store.add(user_id=user_id, tenant_id=tenant_id, content="I love Python", source_agent="a")
        store.add(user_id=user_id, tenant_id=tenant_id, content="salary 200k", source_agent="a")
        out = store.query(user_id=user_id, query_text="python developer", top_k=2)
        assert len(out) == 2
        assert out[0].content == "I love Python"

    def test_query_filters_by_type(self, store, user_id, tenant_id):
        store.add(user_id=user_id, tenant_id=tenant_id, content="x", source_agent="a", type=MemoryType.FACT)
        store.add(user_id=user_id, tenant_id=tenant_id, content="y", source_agent="a", type=MemoryType.PREFERENCE)
        out = store.query(user_id=user_id, query_text="y", top_k=10, types=[MemoryType.PREFERENCE])
        assert len(out) == 1
        assert out[0].type == MemoryType.PREFERENCE

    def test_query_touches_memories(self, store, user_id, tenant_id):
        m = store.add(user_id=user_id, tenant_id=tenant_id, content="x", source_agent="a")
        store.query(user_id=user_id, query_text="x", top_k=1)
        m2 = store.get(m.id)
        assert m2.access_count >= 1

    def test_link_creates_edge(self, store, user_id, tenant_id):
        a = store.add(user_id=user_id, tenant_id=tenant_id, content="a", source_agent="a")
        b = store.add(user_id=user_id, tenant_id=tenant_id, content="b", source_agent="a")
        link = store.link(a.id, b.id, RelationType.SUPPORTS)
        assert link.relation == RelationType.SUPPORTS
        assert len(store.links_for(a.id)) == 1

    def test_decay_returns_count(self, store, user_id, tenant_id):
        store.add(user_id=user_id, tenant_id=tenant_id, content="x", source_agent="a")
        store.add(user_id=user_id, tenant_id=tenant_id, content="y", source_agent="a")
        n = store.decay(0.95)
        assert n == 2

    def test_forget_by_predicate(self, store, user_id, tenant_id):
        store.add(user_id=user_id, tenant_id=tenant_id, content="keep me", source_agent="a")
        store.add(user_id=user_id, tenant_id=tenant_id, content="forget me", source_agent="a")
        n = store.forget(user_id, predicate=lambda m: "forget" in m.content)
        assert n == 1
        assert len(store.list_for_user(user_id)) == 1

    def test_forget_by_source_agent(self, store, user_id, tenant_id):
        store.add(user_id=user_id, tenant_id=tenant_id, content="x", source_agent="profile_agent")
        store.add(user_id=user_id, tenant_id=tenant_id, content="y", source_agent="clarifier_agent")
        n = store.forget(user_id, source_agent="profile_agent")
        assert n == 1

    def test_forget_by_type(self, store, user_id, tenant_id):
        store.add(user_id=user_id, tenant_id=tenant_id, content="x", source_agent="a", type=MemoryType.FACT)
        store.add(user_id=user_id, tenant_id=tenant_id, content="y", source_agent="a", type=MemoryType.TASK)
        n = store.forget(user_id, type=MemoryType.FACT)
        assert n == 1

    def test_cross_agent_sharing(self, store, user_id, tenant_id):
        """One agent writes a memory; another agent reads it back."""
        store.add(
            user_id=user_id, tenant_id=tenant_id,
            content="prefers remote work", source_agent="profile_agent",
            type=MemoryType.PREFERENCE,
        )
        # Simulate the jobseeker_clarifier agent reading
        out = store.query(user_id=user_id, query_text="work location preference", top_k=5)
        assert any("remote" in m.content for m in out)

    def test_confidence_clamping(self, store, user_id, tenant_id):
        m = store.add(user_id=user_id, tenant_id=tenant_id, content="x", source_agent="a", confidence=2.0)
        assert m.confidence == 1.0
        m2 = store.add(user_id=user_id, tenant_id=tenant_id, content="y", source_agent="a", confidence=-0.5)
        assert m2.confidence == 0.0

    def test_initialize_supabase_noop_when_factory_raises(self, store):
        # Should not raise even if factory fails
        store.init(supabase_client_factory=lambda: (_ for _ in ()).throw(RuntimeError("nope")))

    def test_extract_via_mem0_fallback(self, store, user_id, tenant_id):
        """Without a Mem0 client, we still get heuristic extraction."""
        mems = store.extract_via_mem0(
            user_id=user_id,
            conversation=[
                {"role": "user", "content": "I love Python"},
                {"role": "assistant", "content": "Great!"},
                {"role": "user", "content": "I prefer remote work"},
            ],
            tenant_id=tenant_id,
        )
        # fallback keeps user turns as episodic memories
        assert len(mems) >= 1

    def test_singleton_factory(self):
        a = get_memory_store()
        b = get_memory_store()
        assert a is b
        reset_memory_store()
        c = get_memory_store()
        assert c is not a


# ---------------------------------------------------------------------------
# Decay logic
# ---------------------------------------------------------------------------

class TestDecay:
    def test_decay_reduces_all(self, store, user_id, tenant_id):
        m1 = store.add(user_id=user_id, tenant_id=tenant_id, content="a", source_agent="a")
        m2 = store.add(user_id=user_id, tenant_id=tenant_id, content="b", source_agent="a")
        store.decay(0.5)
        assert store.get(m1.id).decay_score < 1.0
        assert store.get(m2.id).decay_score < 1.0

    def test_decay_floor_at_zero(self, store, user_id, tenant_id):
        m = store.add(user_id=user_id, tenant_id=tenant_id, content="a", source_agent="a")
        for _ in range(20):
            store.decay(0.5)
        assert store.get(m.id).decay_score >= 0.0

    def test_decay_queried_less_penalised(self, store, user_id, tenant_id):
        m1 = store.add(user_id=user_id, tenant_id=tenant_id, content="a", source_agent="a")
        m2 = store.add(user_id=user_id, tenant_id=tenant_id, content="b", source_agent="a")
        # query m2 a few times to keep its decay_score up
        for _ in range(5):
            store.query(user_id=user_id, query_text="b", top_k=1)
        store.decay(0.5)
        d1 = store.get(m1.id).decay_score
        d2 = store.get(m2.id).decay_score
        # m2 was touched, so it should have a higher decay_score than m1
        assert d2 >= d1


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------

class TestExtractor:
    def test_extract_preference(self):
        ex = EntityExtractor()
        out = ex.extract([{"role": "user", "content": "I prefer remote work."}])
        assert any(it["type"] == MemoryType.PREFERENCE for it in out)

    def test_extract_fact(self):
        ex = EntityExtractor()
        out = ex.extract([{"role": "user", "content": "I am a software engineer."}])
        assert any(it["type"] == MemoryType.FACT for it in out)

    def test_extract_event(self):
        ex = EntityExtractor()
        out = ex.extract([{"role": "user", "content": "Yesterday I interviewed at Acme."}])
        assert any(it["type"] == MemoryType.EVENT for it in out)

    def test_extract_dedup(self):
        ex = EntityExtractor()
        out = ex.extract([{"role": "user", "content": "I prefer remote. I prefer remote!"}])
        contents = [it["content"].lower() for it in out]
        assert len(contents) == len(set(contents))

    def test_extract_skips_assistant(self):
        ex = EntityExtractor()
        out = ex.extract([{"role": "assistant", "content": "I prefer remote."}])
        assert out == []

    def test_extract_max_items(self):
        ex = EntityExtractor()
        out = ex.extract(
            [{"role": "user", "content": "I prefer " + "x. " * 20}]
        )
        assert len(out) <= 16

    def test_patterns_compile(self):
        # Just ensure patterns don't crash on weird unicode
        for pat in _FACT_PATTERNS + _PREFERENCE_PATTERNS:
            pat.findall("我的名字是张三, 我在 2026 年 1 月 1 日入职")


# ---------------------------------------------------------------------------
# MemoryInjector
# ---------------------------------------------------------------------------

class TestInjector:
    def test_inject_prepends_block(self, store, user_id, tenant_id):
        store.add(user_id=user_id, tenant_id=tenant_id, content="prefers remote work", source_agent="a", type=MemoryType.PREFERENCE)
        injector = MemoryInjector(store)
        out = injector.inject(
            messages=[{"role": "system", "content": "you are helpful"}, {"role": "user", "content": "hi"}],
            user_id=user_id,
            query_text="work preferences",
        )
        assert "MEMORY CONTEXT" in out[0]["content"]
        assert "prefers remote work" in out[0]["content"]

    def test_inject_creates_system_if_missing(self, store, user_id, tenant_id):
        store.add(user_id=user_id, tenant_id=tenant_id, content="loves python", source_agent="a")
        injector = MemoryInjector(store)
        out = injector.inject(
            messages=[{"role": "user", "content": "hi"}],
            user_id=user_id,
            query_text="python",
        )
        assert out[0]["role"] == "system"
        assert "loves python" in out[0]["content"]

    def test_inject_empty_when_no_relevant(self, store, user_id, tenant_id):
        injector = MemoryInjector(store)
        block = injector.build_context_block(user_id=user_id, query_text="xyz")
        assert block == ""


# ---------------------------------------------------------------------------
# EventBus subscribers
# ---------------------------------------------------------------------------

class TestSubscribers:
    def test_profile_updated_writes_facts(self, store, user_id, tenant_id):
        bus = InMemoryEventBus()
        set_event_bus(bus)
        install_memory_subscribers(store)
        bus.publish(Event(name="profile.updated", payload={
            "user_id": str(user_id),
            "tenant_id": str(tenant_id),
            "fields": {"name": "Alice", "location": "Shanghai"},
        }))
        items = store.list_for_user(user_id)
        assert len(items) == 2
        assert any(m.content == "name: Alice" for m in items)
        assert any(m.content == "location: Shanghai" for m in items)

    def test_preference_expressed_writes_preference(self, store, user_id, tenant_id):
        bus = InMemoryEventBus()
        set_event_bus(bus)
        install_memory_subscribers(store)
        bus.publish(Event(name="preference.expressed", payload={
            "user_id": str(user_id),
            "tenant_id": str(tenant_id),
            "content": "wants remote",
        }))
        items = store.list_for_user(user_id, types=[MemoryType.PREFERENCE])
        assert len(items) == 1
        assert items[0].content == "wants remote"

    def test_interview_completed_writes_event(self, store, user_id, tenant_id):
        bus = InMemoryEventBus()
        set_event_bus(bus)
        install_memory_subscribers(store)
        bus.publish(Event(name="interview.completed", payload={
            "user_id": str(user_id),
            "tenant_id": str(tenant_id),
            "role": "Senior Engineer",
            "outcome": "passed",
        }))
        items = store.list_for_user(user_id, types=[MemoryType.EVENT])
        assert len(items) == 1
        assert "Senior Engineer" in items[0].content

    def test_offer_received_writes_high_confidence(self, store, user_id, tenant_id):
        bus = InMemoryEventBus()
        set_event_bus(bus)
        install_memory_subscribers(store)
        bus.publish(Event(name="offer.received", payload={
            "user_id": str(user_id),
            "tenant_id": str(tenant_id),
            "company": "Acme",
            "role": "Staff",
        }))
        items = store.list_for_user(user_id, types=[MemoryType.EVENT])
        assert len(items) == 1
        assert items[0].confidence == 1.0

    def test_decay_requested_triggers_decay(self, store, user_id, tenant_id):
        bus = InMemoryEventBus()
        set_event_bus(bus)
        install_memory_subscribers(store)
        m = store.add(user_id=user_id, tenant_id=tenant_id, content="x", source_agent="a")
        original = store.get(m.id).decay_score
        bus.publish(Event(name="memory.decay.requested", payload={"factor": 0.5}))
        assert store.get(m.id).decay_score < original


# ---------------------------------------------------------------------------
# Agent adapter
# ---------------------------------------------------------------------------

class _StubAgent:
    """Stand-in for a BaseAgent that simply echoes its input."""
    name = "stub_agent"
    description = "stub"
    required_personas = ()

    def __init__(self):
        self.llm = None
        self.memory = None
        self.tracer = None

    async def run(self, agent_input):
        # Capture the context for assertion in tests
        captured = (agent_input.context or {}).get("memory_context", "")
        out = type("O", (), {})()
        out.agent_name = self.name
        out.text = "ok"
        out.artifacts = {"memory_context_preview": captured[:200]}
        out.memory_writes = [
            {"scope": "working", "key": "last_pref", "value": "remote", "confidence": 0.9}
        ]
        out.signals = []
        out.cost_cents = 0
        out.tokens_used = 0
        out.request_id = getattr(agent_input, "request_id", "")
        out.duration_ms = 1
        out.success = True
        out.error = None
        out.reasoning_chain = []
        return out


class TestAgentAdapter:
    def test_memory_aware_run_injects_block(self, store, user_id, tenant_id):
        store.add(user_id=user_id, tenant_id=tenant_id, content="loves python", source_agent="a")
        agent = _StubAgent()

        from agents.runtime import AgentInput
        ai = AgentInput(
            user_id=str(user_id),
            persona="jobseeker",
            text="tell me about python",
            context={"tenant_id": str(tenant_id)},
        )
        out = asyncio.run(memory_aware_run(agent, ai, store=store))
        assert "MEMORY CONTEXT" in out.artifacts["memory_context"]
        # legacy memory_writes should have been persisted as a FACT
        items = store.list_for_user(user_id, types=[MemoryType.FACT])
        assert any("last_pref" in m.content for m in items)

    def test_memory_aware_agent_wrapper(self, store, user_id, tenant_id):
        store.add(user_id=user_id, tenant_id=tenant_id, content="knows Go", source_agent="a")
        wrapped = MemoryAwareAgent(_StubAgent(), store=store)

        from agents.runtime import AgentInput
        ai = AgentInput(
            user_id=str(user_id),
            persona="jobseeker",
            text="golang",
        )
        out = asyncio.run(wrapped.run(ai))
        assert out.success

    def test_memory_aware_run_handles_missing_user(self, store):
        agent = _StubAgent()
        from agents.runtime import AgentInput
        ai = AgentInput(
            user_id="not-a-uuid",
            persona="jobseeker",
            text="hi",
        )
        # Should not raise — coerce_uuid falls back to random uuid
        out = asyncio.run(memory_aware_run(agent, ai, store=store))
        assert out.success


# ---------------------------------------------------------------------------
# API tests (FastAPI TestClient)
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client(monkeypatch):
    """Build a TestClient around a FastAPI app with the memory router."""
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.memory import router as memory_router
    except Exception as e:  # pragma: no cover
        pytest.skip(f"FastAPI not available: {e}")

    from api.auth import CurrentUser
    from api.auth import get_current_user

    app = FastAPI()
    app.include_router(memory_router, prefix="/api/memory", tags=["memory"])

    fake_user = CurrentUser(
        id=uuid.uuid4(),
        email="t@example.com",
        tenant_id=uuid.uuid4(),
        role="talent_partner",
    )

    def _override_user():
        return fake_user

    app.dependency_overrides[get_current_user] = _override_user
    reset_memory_store()
    client = TestClient(app)
    yield client, fake_user
    reset_memory_store()


class TestMemoryAPI:
    def test_health(self, api_client):
        client, _ = api_client
        r = client.get("/api/memory/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "store" in body["components"]

    def test_create_and_list(self, api_client):
        client, user = api_client
        r = client.post("/api/memory/memories", json={
            "content": "loves Python",
            "type": "preference",
            "source_agent": "test_agent",
            "confidence": 0.8,
        })
        assert r.status_code == 200
        created = r.json()
        assert created["content"] == "loves Python"
        r2 = client.get("/api/memory/memories")
        assert r2.status_code == 200
        assert len(r2.json()) == 1

    def test_query(self, api_client):
        client, _ = api_client
        for c in ("loves Python", "prefers remote", "5y experience"):
            client.post("/api/memory/memories", json={
                "content": c, "type": "fact", "source_agent": "t",
            })
        r = client.post("/api/memory/memories/query", json={
            "query_text": "python programming",
            "top_k": 2,
        })
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 2
        assert items[0]["content"] == "loves Python"

    def test_patch(self, api_client):
        client, _ = api_client
        m = client.post("/api/memory/memories", json={
            "content": "x", "type": "fact", "source_agent": "t",
        }).json()
        r = client.patch(f"/api/memory/memories/{m['id']}", json={"content": "y"})
        assert r.status_code == 200
        assert r.json()["content"] == "y"

    def test_delete(self, api_client):
        client, _ = api_client
        m = client.post("/api/memory/memories", json={
            "content": "x", "type": "fact", "source_agent": "t",
        }).json()
        r = client.delete(f"/api/memory/memories/{m['id']}")
        assert r.status_code == 200
        r2 = client.get(f"/api/memory/memories/{m['id']}")
        assert r2.status_code == 404

    def test_forget(self, api_client):
        client, _ = api_client
        client.post("/api/memory/memories", json={
            "content": "a", "type": "fact", "source_agent": "agentA",
        })
        client.post("/api/memory/memories", json={
            "content": "b", "type": "preference", "source_agent": "agentB",
        })
        r = client.post("/api/memory/memories/forget", json={"source_agent": "agentA"})
        assert r.status_code == 200
        assert r.json()["deleted"] == 1

    def test_extract(self, api_client):
        client, _ = api_client
        r = client.post("/api/memory/memories/extract", json={
            "messages": [
                {"role": "user", "content": "I prefer remote work."},
                {"role": "user", "content": "I am a software engineer."},
            ],
            "persist": True,
        })
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 1

    def test_decay(self, api_client):
        client, _ = api_client
        client.post("/api/memory/memories", json={
            "content": "x", "type": "fact", "source_agent": "t",
        })
        r = client.post("/api/memory/memories/decay", json={"factor": 0.5})
        assert r.status_code == 200
        assert r.json()["affected"] >= 1

    def test_link_roundtrip(self, api_client):
        client, _ = api_client
        a = client.post("/api/memory/memories", json={"content": "a", "type": "fact", "source_agent": "t"}).json()
        b = client.post("/api/memory/memories", json={"content": "b", "type": "fact", "source_agent": "t"}).json()
        r = client.post("/api/memory/memories/links", json={
            "memory_id_a": a["id"], "memory_id_b": b["id"], "relation": "supports",
        })
        assert r.status_code == 200
        r2 = client.get(f"/api/memory/memories/{a['id']}/links")
        assert r2.status_code == 200
        assert len(r2.json()) == 1

    def test_access_log(self, api_client):
        client, _ = api_client
        client.post("/api/memory/memories", json={"content": "x", "type": "fact", "source_agent": "t"})
        r = client.get("/api/memory/access-log")
        assert r.status_code == 200
        assert len(r.json()) >= 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_query_with_min_confidence(self, store, user_id, tenant_id):
        store.add(user_id=user_id, tenant_id=tenant_id, content="high conf", source_agent="a", confidence=0.9)
        store.add(user_id=user_id, tenant_id=tenant_id, content="low conf", source_agent="a", confidence=0.1)
        out = store.query(user_id=user_id, query_text="conf", top_k=10, min_confidence=0.5)
        assert all(m.confidence >= 0.5 for m in out)
        assert len(out) == 1

    def test_list_for_user_excludes_archived_by_default(self, store, user_id, tenant_id):
        m = store.add(user_id=user_id, tenant_id=tenant_id, content="x", source_agent="a")
        m.is_archived = True
        store.backend.update(m)
        out = store.list_for_user(user_id)
        assert all(not x.is_archived for x in out)

    def test_get_returns_none_for_missing(self, store):
        assert store.get(uuid.uuid4()) is None

    def test_extract_empty_messages(self):
        ex = EntityExtractor()
        assert ex.extract([]) == []

    def test_extract_skips_empty_content(self):
        ex = EntityExtractor()
        out = ex.extract([{"role": "user", "content": "   "}])
        assert out == []


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
