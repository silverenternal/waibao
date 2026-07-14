"""v10.0 T5012 — Tiered response cache for AI hot paths.

Three logical caches, each with a deliberately different TTL so we trade
freshness against cost in proportion to how expensive / how volatile the
underlying data is:

================  ===========================  ===========================
Cache tier        Typical payload              Default TTL
================  ===========================  ===========================
``llm``           LLM chat / completion        1 hour   (3600s)
                  responses (deterministic
                  given the same prompt)
``rag``           RAG retrieval results        5 minutes (300s)
                  (chunks from Qdrant /
                   Supabase)
``mem0``          Mem0 long-term memory        1 day     (86400s)
                  recall
================  ===========================  ===========================

Backend
-------
The cache is **backend-pluggable** with an automatic in-memory fallback:

* if a Redis client is reachable (``REDIS_URL`` set + ``redis`` installed),
  we use it as the shared, cross-process cache;
* otherwise (or if Redis errors at runtime) we degrade to a thread-safe
  in-process LRU+TTL dict so the service still works in CI / dev / a
  degraded Redis scenario.

All cache operations are **best-effort**: a cache miss, a Redis timeout, or a
serialisation failure MUST NEVER surface to the caller — the wrapped function
simply runs uncached.  This matches the contract of the existing
``services/observability/llm_cache.py``.

Usage
-----
    from services.platform.cache import cached, CacheTier

    @cached(CacheTier.LLM, key=lambda q, **kw: f"chat:{q}")
    def chat(prompt: str, **kw) -> str: ...

    # or the explicit API
    from services.platform.cache import get_cache
    cache = get_cache(CacheTier.RAG)
    hit = cache.get("rag:q123")
"""
from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger("recruittech.platform.cache")

REDIS_URL = os.getenv("REDIS_URL", "").strip()
DEFAULT_MAX_SIZE = int(os.getenv("CACHE_MAX_SIZE", "10000"))


# ===========================================================================
# Tier definitions
# ===========================================================================
class CacheTier(Enum):
    """The three logical caches with their canonical TTLs (seconds)."""

    LLM = ("llm", 3600)       # 1 hour  — deterministic LLM completions
    RAG = ("rag", 300)        # 5 min   — retrieved knowledge chunks
    MEM0 = ("mem0", 86400)    # 1 day   — long-term agent memory

    def __init__(self, prefix: str, ttl: int) -> None:
        self.prefix = prefix
        self.ttl = ttl


# Override TTLs via env (minutes) without touching code, for ops tuning.
def _env_ttl(tier: CacheTier) -> int:
    env_name = f"CACHE_TTL_{tier.name}"
    raw = os.getenv(env_name, "").strip()
    if raw:
        try:
            # value is in SECONDS to match the in-code constants
            return max(int(raw), 1)
        except ValueError:  # noqa: BLE001
            logger.warning("cache.bad_env_ttl %s=%r using default", env_name, raw)
    return tier.ttl


# ===========================================================================
# Backend abstraction
# ===========================================================================
class _Backend:
    """Cache backend interface (get / set / size / ping)."""

    name: str = "base"

    def get(self, key: str) -> Optional[Any]:
        raise NotImplementedError

    def set(self, key: str, value: Any, ttl_seconds: int) -> bool:
        raise NotImplementedError

    def delete(self, key: str) -> bool:
        raise NotImplementedError

    def size(self) -> int:
        raise NotImplementedError

    def ping(self) -> bool:
        raise NotImplementedError


class InMemoryBackend(_Backend):
    """Thread-safe LRU + TTL dict (the always-available fallback)."""

    name = "memory"

    def __init__(self, max_size: int = DEFAULT_MAX_SIZE) -> None:
        self.max_size = max_size
        self._store: "OrderedDict[str, tuple[Any, float]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, exp = entry
            if exp <= now:
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)  # LRU bump
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
        except Exception:  # noqa: BLE001 — never break the caller
            logger.warning("cache.memory.set_failed key=%s", key[:12])
            return False

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._store.pop(key, None) is not None

    def size(self) -> int:
        with self._lock:
            return len(self._store)

    def ping(self) -> bool:
        return True


class RedisBackend(_Backend):
    """Redis-backed cache. JSON-serialised values, per-tier key prefix."""

    name = "redis"

    def __init__(self, client: Any) -> None:
        self._client = client

    @classmethod
    def from_url(cls, url: str) -> Optional["RedisBackend"]:
        if not url:
            return None
        try:
            import redis  # type: ignore  # optional dependency

            return cls(redis.from_url(url, socket_timeout=1.0,
                                      socket_connect_timeout=1.0))
        except Exception:  # noqa: BLE001 — optional dep / network
            logger.info("cache.redis.unavailable url=%s", url[:24])
            return None

    def get(self, key: str) -> Optional[Any]:
        try:
            raw = self._client.get(key)
        except Exception:  # noqa: BLE001
            logger.warning("cache.redis.get_failed key=%s", key[:12])
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw  # tolerate non-JSON stored by other writers

    def set(self, key: str, value: Any, ttl_seconds: int) -> bool:
        try:
            payload = json.dumps(value, default=str)
            self._client.set(key, payload, ex=max(ttl_seconds, 1))
            return True
        except (TypeError, ValueError):
            # value not JSON-serialisable — skip caching rather than crash
            logger.warning("cache.redis.serialize_failed key=%s", key[:12])
            return False
        except Exception:  # noqa: BLE001
            logger.warning("cache.redis.set_failed key=%s", key[:12])
            return False

    def delete(self, key: str) -> bool:
        try:
            self._client.delete(key)
            return True
        except Exception:  # noqa: BLE001
            return False

    def size(self) -> int:
        try:
            return int(self._client.dbsize())
        except Exception:  # noqa: BLE001
            return -1

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:  # noqa: BLE001
            return False


# ===========================================================================
# Per-tier cache facade (one backend per tier, lazily initialised)
# ===========================================================================
_backends: dict[str, _Backend] = {}
_backends_lock = threading.Lock()


def _build_backend(tier: CacheTier) -> _Backend:
    """Pick Redis when healthy, else the in-memory fallback."""
    redis_b = RedisBackend.from_url(REDIS_URL)
    if redis_b is not None and redis_b.ping():
        return redis_b
    if redis_b is not None:
        logger.info("cache.falling_back_to_memory tier=%s (redis ping failed)",
                    tier.name)
    return InMemoryBackend()


def get_backend(tier: CacheTier) -> _Backend:
    """Return the backend for a tier (cached singleton, thread-safe)."""
    key = tier.prefix
    with _backends_lock:
        b = _backends.get(key)
        if b is None:
            b = _build_backend(tier)
            _backends[key] = b
        return b


# exposed for tests to inject a fresh backend
def _reset_backends() -> None:
    with _backends_lock:
        _backends.clear()


# ===========================================================================
# Key derivation
# ===========================================================================
def make_key(tier: CacheTier, raw: str) -> str:
    """Stable, length-bounded key: ``<tier>:sha256(raw)[:16]``."""
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{tier.prefix}:{digest}"


# ===========================================================================
# High-level API
# ===========================================================================
class TieredCache:
    """Thin facade exposing get/set/delete/size for a single tier."""

    def __init__(self, tier: CacheTier) -> None:
        self.tier = tier

    @property
    def ttl(self) -> int:
        return _env_ttl(self.tier)

    @property
    def backend(self) -> _Backend:
        return get_backend(self.tier)

    def get(self, raw_key: str) -> Optional[Any]:
        return self.backend.get(make_key(self.tier, raw_key))

    def set(self, raw_key: str, value: Any, ttl: Optional[int] = None) -> bool:
        return self.backend.set(make_key(self.tier, raw_key), value,
                                ttl if ttl is not None else self.ttl)

    def delete(self, raw_key: str) -> bool:
        return self.backend.delete(make_key(self.tier, raw_key))

    def size(self) -> int:
        return self.backend.size()


def get_cache(tier: CacheTier) -> TieredCache:
    return TieredCache(tier)


# ===========================================================================
# Decorator: @cached(tier, key=...)
# ===========================================================================
def cached(
    tier: CacheTier,
    key: Optional[Callable[..., str]] = None,
    ttl: Optional[int] = None,
) -> Callable[[Callable], Callable]:
    """Memoise a function's return value in the given cache tier.

    ``key`` is a callable that receives the same args/kwargs and returns the
    raw key string.  When omitted, a key is synthesised from the repr of the
    bound arguments (good enough for simple pure functions).

    Failures (backend error / unserialisable value) degrade gracefully: the
    wrapped function runs uncached and its result is returned.
    """
    def decorator(fn: Callable) -> Callable:
        cache = get_cache(tier)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                raw_key = key(*args, **kwargs) if key else _default_key(fn, args, kwargs)
            except Exception:  # noqa: BLE001 — key fn must not break caller
                return fn(*args, **kwargs)

            # cache reads are best-effort: a backend error degrades to a miss
            try:
                hit = cache.get(raw_key)
            except Exception:  # noqa: BLE001
                logger.debug("cache.get_failed tier=%s fn=%s", tier.name, fn.__name__)
                hit = None
            if hit is not None:
                logger.debug("cache.hit tier=%s fn=%s", tier.name, fn.__name__)
                return hit

            result = fn(*args, **kwargs)
            try:
                cache.set(raw_key, result, ttl)
            except Exception:  # noqa: BLE001
                logger.debug("cache.set_failed tier=%s fn=%s", tier.name, fn.__name__)
            return result

        # expose internals for tests / introspection
        wrapper._cache = cache  # type: ignore[attr-defined]
        wrapper._tier = tier    # type: ignore[attr-defined]
        return wrapper

    return decorator


def _default_key(fn: Callable, args: tuple, kwargs: dict) -> str:
    parts = [fn.__module__ or "", fn.__qualname__, repr(args), repr(kwargs)]
    return "|".join(parts)


# ===========================================================================
# Health / observability
# ===========================================================================
def cache_status() -> dict:
    """Snapshot every tier's backend name + size, for /healthz."""
    out: dict[str, dict] = {}
    for tier in CacheTier:
        b = get_backend(tier)
        out[tier.name] = {
            "backend": b.name,
            "size": b.size(),
            "ttl_seconds": _env_ttl(tier),
        }
    return out
