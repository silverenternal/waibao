"""LLM 调用缓存 — T806.

特性:
- key = sha256(provider + model + messages + temperature + 其他签名参数)
- Redis backend (有 redis client 时) 用 Redis LRU + TTL (默认 24h)
- 自动 fallback 到进程内 LRU + TTL dict (无论 redis 缺失/redis 失败/写失败)
- 命中率统计 (hit/miss/size) — 与 cost dashboard 暴露
- 写失败只记 warn 日志,不影响业务调用方
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Iterable, Optional

logger = logging.getLogger("recruittech.services.llm_cache")

DEFAULT_TTL_SECONDS = int(os.getenv("LLM_CACHE_TTL", "86400"))  # 24h
DEFAULT_MAX_SIZE = int(os.getenv("LLM_CACHE_MAX_SIZE", "10000"))
REDIS_URL = os.getenv("REDIS_URL", "")  # 例如: redis://localhost:6379/0


# ---------------------------------------------------------------------------
# Backend abstraction
# ---------------------------------------------------------------------------
class _Backend:
    """Cache backend 抽象接口."""

    def get(self, key: str) -> Optional[Any]:
        raise NotImplementedError

    def set(self, key: str, value: Any, ttl_seconds: int) -> bool:
        """返回 True=成功 False=失败 (失败应 fallback / 不抛)."""
        raise NotImplementedError

    def size(self) -> int:
        raise NotImplementedError

    def ping(self) -> bool:
        raise NotImplementedError


class InMemoryBackend(_Backend):
    """进程内 LRU + TTL,deque-style OrderedDict 实现真 LRU."""

    def __init__(self, max_size: int) -> None:
        self.max_size = max_size
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            value, exp = entry
            if exp <= now:
                self._store.pop(key, None)
                return None
            # LRU bump
            self._store.move_to_end(key)
            return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> bool:
        try:
            with self._lock:
                exp = time.time() + max(ttl_seconds, 1)
                if key in self._store:
                    self._store.move_to_end(key)
                self._store[key] = (value, exp)
                while len(self._store) > self.max_size:
                    self._store.popitem(last=False)
            return True
        except Exception:  # noqa: BLE001 - 写失败不影响业务
            logger.warning("llm_cache.in_memory.set_failed key=%s", key[:12])
            return False

    def size(self) -> int:
        with self._lock:
            return len(self._store)

    def ping(self) -> bool:
        return True


class RedisBackend(_Backend):
    """基于 redis-py 的 cache backend (可选依赖)."""

    def __init__(self, url: str, namespace: str = "llm_cache:") -> None:
        self.url = url
        self.namespace = namespace
        self._client = None
        self._healthy = False
        try:
            import redis  # type: ignore[import-not-found]

            self._client = redis.Redis.from_url(url, decode_responses=False, socket_timeout=2)
            self._client.ping()
            self._healthy = True
            logger.info("llm_cache.redis.connected url=%s", url)
        except Exception as exc:  # noqa: BLE001 - 缺失依赖/连接失败均正常
            logger.info("llm_cache.redis.unavailable url=%s err=%s", url, exc)
            self._client = None
            self._healthy = False

    def ping(self) -> bool:
        if not self._client:
            return False
        try:
            return bool(self._client.ping())
        except Exception:  # noqa: BLE001
            self._healthy = False
            return False

    def _full_key(self, key: str) -> str:
        return f"{self.namespace}{key}"

    def get(self, key: str) -> Optional[Any]:
        if not self._client or not self._healthy:
            return None
        try:
            raw = self._client.get(self._full_key(key))
            if not raw:
                return None
            return json.loads(raw)
        except Exception:  # noqa: BLE001 - redis error -> None (cache miss semantic)
            self._healthy = False
            logger.warning("llm_cache.redis.get_failed key=%s", key[:12])
            return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> bool:
        if not self._client or not self._healthy:
            return False
        try:
            payload = json.dumps(value, ensure_ascii=False, default=str)
            self._client.set(self._full_key(key), payload, ex=max(ttl_seconds, 1))
            return True
        except Exception:  # noqa: BLE001
            self._healthy = False
            logger.warning("llm_cache.redis.set_failed key=%s", key[:12])
            return False

    def size(self) -> int:
        if not self._client or not self._healthy:
            return 0
        try:
            return int(self._client.dbsize())
        except Exception:  # noqa: BLE001
            return 0


# ---------------------------------------------------------------------------
# Unified cache facade
# ---------------------------------------------------------------------------
class LLMCache:
    """LLM 调用缓存: 优先 Redis, 不可用时 fallback in-memory.

    只统计 hit/miss,对调用方透明.
    """

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_size: int = DEFAULT_MAX_SIZE,
        redis_url: Optional[str] = None,
    ) -> None:
        self.ttl = ttl_seconds
        self.max_size = max_size
        url = redis_url if redis_url is not None else REDIS_URL
        self._redis: Optional[RedisBackend] = None
        self._memory = InMemoryBackend(max_size)
        if url:
            self._redis = RedisBackend(url)
            if not self._redis.ping():
                logger.info("llm_cache.fallback_memory reason=redis_unavailable")
                self._redis = None
        self._stats_lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._writes = 0
        self._write_failures = 0
        self._fallback_uses = 0

    # ----- key derivation ------------------------------------------------
    @staticmethod
    def _canonical_messages(messages: Any) -> str:
        if isinstance(messages, list):
            try:
                return json.dumps(messages, sort_keys=True, ensure_ascii=False)
            except (TypeError, ValueError):
                # 兜底:每个 message 拆开序列化
                return json.dumps(
                    [m if isinstance(m, (str, int, float, bool)) else str(m) for m in messages],
                    sort_keys=True,
                )
        return str(messages)

    @classmethod
    def make_key(
        cls,
        provider: str,
        model: str,
        messages: Any,
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> str:
        """key = sha256(provider + model + canonical(messages) + temperature + sorted kwargs)."""
        h = hashlib.sha256()
        h.update(f"{provider}|{model}|".encode("utf-8"))
        h.update(cls._canonical_messages(messages).encode("utf-8"))
        if temperature is not None:
            h.update(f"|temp={temperature}".encode("utf-8"))
        if kwargs:
            h.update(b"|")
            h.update(
                json.dumps(kwargs, sort_keys=True, default=str, ensure_ascii=False).encode(
                    "utf-8"
                )
            )
        return h.hexdigest()

    # ----- public API ----------------------------------------------------
    def get(self, key: str) -> Optional[Any]:
        """读取 cache value; 返回 None 表示 miss. 同时计入 hit/miss stats."""
        value = None
        if self._redis is not None:
            value = self._redis.get(key)
        if value is None and self._redis is not None:
            # 如果 redis 返回 None,回退到 memory (例如 redis 重启后) 仍能命中.
            pass
        if value is None:
            value = self._memory.get(key)
        with self._stats_lock:
            if value is not None:
                self._hits += 1
            else:
                self._misses += 1
        return value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
        """写入缓存,失败仅记 log,不抛."""
        ttl = ttl_seconds or self.ttl
        ok = False
        # Redis 主写
        if self._redis is not None:
            ok = self._redis.set(key, value, ttl)
        # 同时写 memory 双层 (只要 redis 命中就不用查内存;但写即同步,简化逻辑)
        mem_ok = self._memory.set(key, value, ttl)
        with self._stats_lock:
            self._writes += 1
            if not ok and not mem_ok:
                self._write_failures += 1
        return ok or mem_ok

    def stats(self) -> dict[str, Any]:
        with self._stats_lock:
            hits, misses, writes, fail = self._hits, self._misses, self._writes, self._write_failures
        total = hits + misses
        return {
            "ttl_seconds": self.ttl,
            "max_size": self.max_size,
            "size": self._memory.size(),
            "memory_size": self._memory.size(),
            "redis_size": self._redis.size() if self._redis else 0,
            "redis_healthy": (self._redis.ping() if self._redis else False),
            "hits": hits,
            "misses": misses,
            "writes": writes,
            "write_failures": fail,
            "hit_rate": (hits / total) if total > 0 else 0.0,
            "total_requests": total,
        }

    def reset_stats(self) -> None:
        with self._stats_lock:
            self._hits = 0
            self._misses = 0
            self._writes = 0
            self._write_failures = 0
            self._fallback_uses = 0


# 全局单例 (与 v3.0 之前的内存版兼容)
llm_cache = LLMCache()


# ---------------------------------------------------------------------------
# Decorator — 兼容 with_resilience 流程: 先查 cache 再调 provider
# ---------------------------------------------------------------------------
def llm_cache_decorator(
    cache: Optional[LLMCache] = None,
    provider: str = "openai",
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    ttl_seconds: Optional[int] = None,
    key_extractor: Optional[callable] = None,  # type: ignore[type-arg]
) -> callable:  # type: ignore[type-arg]
    """装饰器: 包裹异步 LLM 调用,自动 cache.

    用法:
        @llm_cache_decorator(provider="openai", model="gpt-4o")
        async def call_llm(messages, temperature=0.7): ...
    """
    import functools

    cache = cache or llm_cache

    def decorator(fn):  # type: ignore[type-arg]
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            nonlocal model, temperature
            model_name = model or kwargs.get("model", "unknown")
            temp_val = kwargs.get("temperature", temperature)
            messages = kwargs.get("messages") or (args[0] if args else [])
            key = (key_extractor(messages, kwargs) if key_extractor else
                   cache.make_key(provider, model_name, messages, temp_val))
            cached = cache.get(key)
            if cached is not None:
                return cached
            result = await fn(*args, **kwargs)
            try:
                cache.set(key, result, ttl_seconds=ttl_seconds)
            except Exception:  # noqa: BLE001 - 写失败不影响业务
                logger.warning("llm_cache.decorator.set_failed")
            return result
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------
def get_cache() -> LLMCache:
    return llm_cache


def get_stats() -> dict[str, Any]:
    return llm_cache.stats()


def bulk_make_keys(
    provider: str, model: str, message_batches: Iterable[Any], **kwargs: Any
) -> list[str]:
    return [LLMCache.make_key(provider, model, m, **kwargs) for m in message_batches]
