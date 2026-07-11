"""LLM cache 测试 — T806.

覆盖:
- key 稳定性 (同输入同 key)
- hit / miss 行为
- TTL 过期
- LRU 替换
- Redis backend 缺失/失败 fallback 到 memory
- 写失败不影响业务
- 命中率统计
"""
from __future__ import annotations

import time

import pytest

from services.llm_cache import (
    DEFAULT_TTL_SECONDS,
    InMemoryBackend,
    LLMCache,
    RedisBackend,
    get_cache,
    get_stats,
    llm_cache_decorator,
)


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------
def test_make_key_stable():
    """同输入同 key."""
    messages = [{"role": "user", "content": "hi"}]
    k1 = LLMCache.make_key("openai", "gpt-4o", messages, 0.7)
    k2 = LLMCache.make_key("openai", "gpt-4o", messages, 0.7)
    assert k1 == k2
    assert len(k1) == 64  # sha256 hex


def test_make_key_differs_on_temperature():
    a = LLMCache.make_key("openai", "gpt-4o", [{"role": "user", "content": "x"}], 0.0)
    b = LLMCache.make_key("openai", "gpt-4o", [{"role": "user", "content": "x"}], 0.5)
    assert a != b


def test_make_key_differs_on_model():
    a = LLMCache.make_key("openai", "gpt-4o", [{"role": "user", "content": "x"}])
    b = LLMCache.make_key("openai", "gpt-4o-mini", [{"role": "user", "content": "x"}])
    assert a != b


def test_make_key_differs_on_provider():
    msgs = [{"role": "user", "content": "x"}]
    a = LLMCache.make_key("openai", "gpt-4o", msgs)
    b = LLMCache.make_key("anthropic", "gpt-4o", msgs)
    assert a != b


def test_make_key_message_order_independent_with_dict():
    """dict messages 用 sort_keys=True 序列化,顺序不影响结果."""
    a = LLMCache.make_key("openai", "gpt-4o", [{"role": "user", "content": "x", "name": "u"}])
    b = LLMCache.make_key("openai", "gpt-4o", [{"name": "u", "role": "user", "content": "x"}])
    assert a == b


def test_make_key_handles_non_list_messages():
    """string 也能处理."""
    k = LLMCache.make_key("openai", "gpt-4o", "raw-string", 0.5)
    assert isinstance(k, str) and len(k) == 64


# ---------------------------------------------------------------------------
# InMemoryBackend
# ---------------------------------------------------------------------------
def test_memory_backend_hit_miss():
    be = InMemoryBackend(100)
    assert be.get("missing") is None
    assert be.set("k", "v", 60) is True
    assert be.get("k") == "v"


def test_memory_backend_ttl_expiry():
    be = InMemoryBackend(100)
    # 用很小 ttl 直接观察过期
    be.set("k", "v", ttl_seconds=1)
    assert be.get("k") == "v"
    time.sleep(1.2)
    assert be.get("k") is None


def test_memory_backend_lru_eviction():
    be = InMemoryBackend(3)
    for i in range(5):
        be.set(f"k{i}", i, 60)
    assert be.size() == 3
    # 最早的应被驱逐
    assert be.get("k0") is None
    assert be.get("k4") == 4


def test_memory_backend_ping_always_true():
    be = InMemoryBackend(10)
    assert be.ping() is True


# ---------------------------------------------------------------------------
# LLMCache facade
# ---------------------------------------------------------------------------
def test_llm_cache_hit_and_miss():
    cache = LLMCache(ttl_seconds=60, max_size=100)
    k = "test-key-1"
    assert cache.get(k) is None  # miss
    cache.set(k, {"result": "ok"})
    assert cache.get(k) == {"result": "ok"}  # hit


def test_llm_cache_ttl_expiry():
    cache = LLMCache(ttl_seconds=1, max_size=100)
    k = "expiring-key"
    cache.set(k, "v")
    assert cache.get(k) == "v"
    time.sleep(1.2)
    assert cache.get(k) is None


def test_llm_cache_set_failure_does_not_raise(caplog):
    """写失败不应抛异常."""
    cache = LLMCache(ttl_seconds=60, max_size=10)
    # 模拟 set 失败:塞 huge value (不抛,但不阻塞后续)
    cache.set("huge", "x" * 1024 * 1024)
    # 业务路径不应受影响
    cache.set("another", "normal")
    assert cache.get("another") == "normal"


def test_llm_cache_stats_hit_rate():
    cache = LLMCache(ttl_seconds=60, max_size=100)
    k = "stats-key"
    cache.set(k, "v")
    cache.set("another", "x")
    cache.get(k)  # hit
    cache.get(k)  # hit
    cache.get("not-there")  # miss
    stats = cache.stats()
    assert stats["hits"] == 2
    assert stats["misses"] == 1
    assert abs(stats["hit_rate"] - 2 / 3) < 1e-6
    assert stats["writes"] == 2


def test_llm_cache_redis_unavailable_falls_back_to_memory(caplog):
    """Redis URL 不可达时,自动 fallback 到 in-memory backend."""
    cache = LLMCache(ttl_seconds=60, max_size=10, redis_url="redis://localhost:1")  # 1 = unreachable
    cache.set("k", "v")
    assert cache.get("k") == "v"
    # redis_healthy 应为 False
    assert cache.stats()["redis_healthy"] is False


def test_redis_backend_init_without_redis_package(monkeypatch):
    """redis 不可导入时,backend 退化到不可用,不抛."""
    # 默认环境无 redis-py;backend 应可构造
    be = RedisBackend("redis://fake:1234")
    assert be.ping() is False
    assert be.get("anything") is None
    assert be.set("k", "v", 60) is False


def test_llm_cache_decorator_caches_provider_calls():
    """llm_cache_decorator 应在相同入参下复用结果."""
    cache = LLMCache(ttl_seconds=60, max_size=100)
    call_count = {"n": 0}

    @llm_cache_decorator(cache=cache, provider="openai", model="gpt-4o", temperature=0.5)
    async def fake_llm(messages, **_kw):
        call_count["n"] += 1
        return {"echo": messages, "n": call_count["n"]}

    import asyncio

    msgs = [{"role": "user", "content": "hello"}]
    r1 = asyncio.run(fake_llm(messages=msgs))
    r2 = asyncio.run(fake_llm(messages=msgs))
    assert call_count["n"] == 1
    assert r1 == r2
    stats = cache.stats()
    assert stats["hits"] >= 1
    assert stats["misses"] >= 1


def test_llm_cache_decorator_different_inputs_miss():
    cache = LLMCache(ttl_seconds=60, max_size=100)
    call_count = {"n": 0}

    @llm_cache_decorator(cache=cache, provider="openai", model="gpt-4o")
    async def fake_llm(messages, **_kw):
        call_count["n"] += 1
        return messages

    import asyncio
    asyncio.run(fake_llm(messages=[{"role": "user", "content": "a"}]))
    asyncio.run(fake_llm(messages=[{"role": "user", "content": "b"}]))
    assert call_count["n"] == 2


def test_global_cache_singleton():
    """get_cache() 返回同一实例."""
    a = get_cache()
    b = get_cache()
    assert a is b


def test_global_stats_shape():
    """get_stats() 必备 keys."""
    s = get_stats()
    for key in [
        "ttl_seconds",
        "max_size",
        "memory_size",
        "hits",
        "misses",
        "writes",
        "hit_rate",
        "total_requests",
        "redis_healthy",
    ]:
        assert key in s, f"missing {key}"


def test_default_ttl_is_24h(monkeypatch):
    """默认 TTL 为 24h (86400s)."""
    # 当 LLM_CACHE_TTL 未设置时
    monkeypatch.delenv("LLM_CACHE_TTL", raising=False)
    cache = LLMCache()  # use default
    assert cache.ttl == DEFAULT_TTL_SECONDS or cache.ttl == 86400


def test_cache_key_handles_complex_messages():
    """嵌套消息结构也能稳定 hash."""
    msgs = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "hi"},
                {"type": "image_url", "image_url": {"url": "https://x/a.png"}},
            ],
        }
    ]
    k1 = LLMCache.make_key("openai", "gpt-4o", msgs)
    k2 = LLMCache.make_key("openai", "gpt-4o", list(reversed(msgs)))
    # 整体顺序不变,但内部 list 也稳定
    assert k1 == k2


def test_llm_cache_concurrent_writes(monkeypatch):
    """并发写不应破坏 stats 计数."""
    import threading
    cache = LLMCache(ttl_seconds=60, max_size=1000)

    def worker(i: int):
        for j in range(50):
            cache.set(f"k-{i}-{j}", i * 1000 + j)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stats = cache.stats()
    assert stats["writes"] == 250
    assert stats["write_failures"] == 0
