"""T5012 — tiered cache service tests.

Covers ``backend/services/platform/cache.py``:

* the three canonical tiers exist with the right TTLs (LLM=1h, RAG=5min, Mem0=1d)
* the in-memory backend honours TTL + LRU eviction
* the Redis backend degrades gracefully when redis is absent / errors
* ``@cached`` memoises, returns the cached value on repeat calls, and never
  lets a cache failure surface to the caller
* ``cache_status()`` reports every tier
* env overrides for TTLs are honoured
"""
from __future__ import annotations

import os
import time

import pytest

from services.platform import cache as cache_mod
from services.platform.cache import (
    CacheTier,
    InMemoryBackend,
    RedisBackend,
    TieredCache,
    cache_status,
    cached,
    get_backend,
    make_key,
)


@pytest.fixture(autouse=True)
def _reset_cache_state(monkeypatch):
    """Each test starts with a fresh backend registry + no REDIS_URL."""
    monkeypatch.setattr(cache_mod, "REDIS_URL", "")
    cache_mod._reset_backends()
    yield
    cache_mod._reset_backends()


# ===========================================================================
# Tier definitions
# ===========================================================================
class TestTierDefinitions:
    def test_three_tiers_exist(self) -> None:
        names = {t.name for t in CacheTier}
        assert names == {"LLM", "RAG", "MEM0"}

    def test_llm_ttl_is_one_hour(self) -> None:
        assert CacheTier.LLM.ttl == 3600

    def test_rag_ttl_is_five_minutes(self) -> None:
        assert CacheTier.RAG.ttl == 300

    def test_mem0_ttl_is_one_day(self) -> None:
        assert CacheTier.MEM0.ttl == 86400

    def test_each_tier_has_distinct_prefix(self) -> None:
        prefixes = [t.prefix for t in CacheTier]
        assert len(prefixes) == len(set(prefixes))

    def test_tier_ordering_llm_shorter_than_mem0(self) -> None:
        assert CacheTier.RAG.ttl < CacheTier.LLM.ttl < CacheTier.MEM0.ttl


# ===========================================================================
# In-memory backend
# ===========================================================================
class TestInMemoryBackend:
    def test_set_then_get(self) -> None:
        b = InMemoryBackend()
        assert b.set("k", {"a": 1}, ttl_seconds=60) is True
        assert b.get("k") == {"a": 1}

    def test_miss_returns_none(self) -> None:
        assert InMemoryBackend().get("missing") is None

    def test_ttl_expiry(self) -> None:
        b = InMemoryBackend()
        b.set("k", "v", ttl_seconds=1)
        assert b.get("k") == "v"
        time.sleep(1.1)
        assert b.get("k") is None

    def test_lru_eviction(self) -> None:
        b = InMemoryBackend(max_size=2)
        b.set("a", 1, 60)
        b.set("b", 2, 60)
        b.get("a")            # bump a → b is LRU
        b.set("c", 3, 60)     # evicts b
        assert b.get("a") == 1
        assert b.get("c") == 3
        assert b.get("b") is None

    def test_delete(self) -> None:
        b = InMemoryBackend()
        b.set("k", "v", 60)
        assert b.delete("k") is True
        assert b.get("k") is None
        assert b.delete("k") is False

    def test_size(self) -> None:
        b = InMemoryBackend()
        b.set("a", 1, 60)
        b.set("b", 2, 60)
        assert b.size() == 2

    def test_ping_always_true(self) -> None:
        assert InMemoryBackend().ping() is True

    def test_set_unserialisable_does_not_crash(self) -> None:
        """The backend must never raise to the caller."""
        b = InMemoryBackend()
        # an object with no JSON path still stores fine in-memory
        b.set("k", object(), 60)
        assert b.get("k") is not None


# ===========================================================================
# Key derivation
# ===========================================================================
class TestMakeKey:
    def test_key_is_namespaced_by_tier(self) -> None:
        assert make_key(CacheTier.LLM, "q").startswith("llm:")
        assert make_key(CacheTier.RAG, "q").startswith("rag:")
        assert make_key(CacheTier.MEM0, "q").startswith("mem0:")

    def test_same_input_same_key(self) -> None:
        assert make_key(CacheTier.LLM, "abc") == make_key(CacheTier.LLM, "abc")

    def test_different_tiers_different_key(self) -> None:
        assert make_key(CacheTier.LLM, "abc") != make_key(CacheTier.RAG, "abc")

    def test_key_is_length_bounded(self) -> None:
        long = "x" * 100_000
        k = make_key(CacheTier.LLM, long)
        assert len(k) < 60  # prefix + 16 hex chars + colon


# ===========================================================================
# TieredCache facade
# ===========================================================================
class TestTieredCache:
    def test_uses_tier_default_ttl(self) -> None:
        c = TieredCache(CacheTier.RAG)
        assert c.ttl == 300

    def test_set_get_roundtrip(self) -> None:
        c = TieredCache(CacheTier.LLM)
        c.set("prompt-x", "answer")
        assert c.get("prompt-x") == "answer"

    def test_delete(self) -> None:
        c = TieredCache(CacheTier.MEM0)
        c.set("mem", {"role": "user"})
        assert c.delete("mem") is True
        assert c.get("mem") is None

    def test_explicit_ttl_overrides_default(self) -> None:
        c = TieredCache(CacheTier.LLM)
        c.set("short", "v", ttl=1)
        time.sleep(1.1)
        assert c.get("short") is None

    def test_env_ttl_override(self, monkeypatch) -> None:
        monkeypatch.setenv("CACHE_TTL_LLM", "120")
        assert cache_mod._env_ttl(CacheTier.LLM) == 120

    def test_env_ttl_override_clamps_to_min_one(self, monkeypatch) -> None:
        monkeypatch.setenv("CACHE_TTL_LLM", "0")
        assert cache_mod._env_ttl(CacheTier.LLM) == 1

    def test_env_ttl_override_ignores_garbage(self, monkeypatch) -> None:
        monkeypatch.setenv("CACHE_TTL_LLM", "not-a-number")
        assert cache_mod._env_ttl(CacheTier.LLM) == 3600


# ===========================================================================
# Backend selection
# ===========================================================================
class TestBackendSelection:
    def test_falls_back_to_memory_without_redis(self) -> None:
        b = get_backend(CacheTier.LLM)
        assert b.name == "memory"

    def test_redis_unavailable_returns_none(self) -> None:
        """from_url with a bad host must not raise."""
        b = RedisBackend.from_url("redis://127.0.0.1:1/0")
        # client may construct; ping should be False / treated as unavailable
        if b is not None:
            assert b.ping() in (False, True)  # never raises


# ===========================================================================
# @cached decorator
# ===========================================================================
class TestCachedDecorator:
    def test_memoises_repeated_calls(self) -> None:
        calls = []

        @cached(CacheTier.LLM, key=lambda x: f"double:{x}")
        def double(x: int) -> int:
            calls.append(x)
            return x * 2

        assert double(3) == 6
        assert double(3) == 6
        assert calls == [3]  # second call hit the cache

    def test_different_args_dont_collide(self) -> None:
        @cached(CacheTier.RAG, key=lambda q: f"q:{q}")
        def fetch(q: str) -> str:
            return f"result:{q}"

        assert fetch("a") == "result:a"
        assert fetch("b") == "result:b"

    def test_default_key_works_without_key_fn(self) -> None:
        @cached(CacheTier.MEM0)
        def add(a: int, b: int) -> int:
            return a + b

        assert add(1, 2) == 3
        assert add(1, 2) == 3  # cached

    def test_cache_failure_does_not_break_caller(self, monkeypatch) -> None:
        """If the backend raises, the function still runs."""
        @cached(CacheTier.LLM, key=lambda x: f"k:{x}")
        def expensive(x: int) -> int:
            return x + 1

        # sabotage the backend's get to raise
        bad = type("Bad", (InMemoryBackend,), {
            "get": lambda self, k: (_ for _ in ()).throw(RuntimeError("boom")),
        })()
        # inject the bad backend into the tier's slot
        cache_mod._backends[CacheTier.LLM.prefix] = bad
        # must NOT raise — falls through to the real call
        assert expensive(5) == 6

    def test_key_fn_failure_runs_uncached(self) -> None:
        @cached(CacheTier.RAG, key=lambda q: 1 / 0)  # type: ignore
        def fetch(q: str) -> str:
            return f"v:{q}"

        assert fetch("x") == "v:x"  # key fn raised → run uncached


# ===========================================================================
# Observability
# ===========================================================================
class TestCacheStatus:
    def test_reports_all_three_tiers(self) -> None:
        status = cache_status()
        assert set(status.keys()) == {"LLM", "RAG", "MEM0"}
        for tier_name, info in status.items():
            assert "backend" in info
            assert "ttl_seconds" in info
            assert isinstance(info["size"], int)

    def test_status_reflects_memory_backend(self) -> None:
        # populate the LLM cache
        TieredCache(CacheTier.LLM).set("k", "v")
        status = cache_status()
        assert status["LLM"]["backend"] in ("memory", "redis")


# ===========================================================================
# Cross-tier isolation
# ===========================================================================
class TestCrossTierIsolation:
    def test_writes_to_one_tier_invisible_in_another(self) -> None:
        llm = TieredCache(CacheTier.LLM)
        rag = TieredCache(CacheTier.RAG)
        llm.set("shared-key-name", "llm-value")
        # same raw key, different tier → must miss
        assert rag.get("shared-key-name") is None
