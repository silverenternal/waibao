"""T1807 — Cache 命中率统计 (跨 LLM cache / API key lookup / Webhook dispatch).

设计:
- 轻量级线程/协程安全计数器
- 支持 hit/miss/eviction 三事件
- 提供 per-namespace 命中率 + 总体命中率
- 可挂接到 Prometheus / OpenTelemetry 出口
"""
from __future__ import annotations

import asyncio
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CacheStats:
    """单 namespace 命中率."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    writes: int = 0

    @property
    def total(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        return self.hits / self.total if self.total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "writes": self.writes,
            "total": self.total,
            "hit_rate": round(self.hit_rate, 4),
        }


class CacheMetrics:
    """线程安全的 cache 命中率采集器."""

    def __init__(self) -> None:
        self._stats: dict[str, CacheStats] = defaultdict(CacheStats)
        self._lock = threading.Lock()

    def hit(self, namespace: str = "default") -> None:
        with self._lock:
            self._stats[namespace].hits += 1

    def miss(self, namespace: str = "default") -> None:
        with self._lock:
            self._stats[namespace].misses += 1

    def eviction(self, namespace: str = "default") -> None:
        with self._lock:
            self._stats[namespace].evictions += 1

    def write(self, namespace: str = "default") -> None:
        with self._lock:
            self._stats[namespace].writes += 1

    def get(self, namespace: str) -> CacheStats:
        with self._lock:
            return CacheStats(**self._stats[namespace].__dict__)

    def all_stats(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {k: v.to_dict() for k, v in self._stats.items()}

    def overall(self) -> dict[str, Any]:
        with self._lock:
            total_hits = sum(s.hits for s in self._stats.values())
            total_misses = sum(s.misses for s in self._stats.values())
            total_evictions = sum(s.evictions for s in self._stats.values())
            total_writes = sum(s.writes for s in self._stats.values())
        total = total_hits + total_misses
        return {
            "hits": total_hits,
            "misses": total_misses,
            "evictions": total_evictions,
            "writes": total_writes,
            "total": total,
            "hit_rate": round(total_hits / total, 4) if total else 0.0,
            "namespaces": len(self._stats),
            "sampled_at": datetime.now(timezone.utc).isoformat(),
        }

    def reset(self) -> None:
        with self._lock:
            self._stats.clear()


# 全局单例 — 跨模块共享
_GLOBAL = CacheMetrics()


def get_cache_metrics() -> CacheMetrics:
    return _GLOBAL


def record_hit(namespace: str = "default") -> None:
    _GLOBAL.hit(namespace)


def record_miss(namespace: str = "default") -> None:
    _GLOBAL.miss(namespace)


def record_eviction(namespace: str = "default") -> None:
    _GLOBAL.eviction(namespace)


def record_write(namespace: str = "default") -> None:
    _GLOBAL.write(namespace)


def report() -> dict[str, Any]:
    """完整的命中率报告 — 用于 dashboard / metrics endpoint."""
    return {
        "overall": _GLOBAL.overall(),
        "namespaces": _GLOBAL.all_stats(),
    }


# ---------------------------------------------------------------------------
# 装饰器: 装饰一个 cache lookup 函数自动记录 hit/miss
# ---------------------------------------------------------------------------
from functools import wraps
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


def track_cache(namespace: str) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """装饰一个返回 cached 值的 async 函数;命中或未命中自动记录.

    用法:
        @track_cache("llm")
        async def lookup_cached_response(prompt: str) -> str | None:
            ...
    """
    def deco(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                value = await fn(*args, **kwargs)
            except Exception:
                record_miss(namespace)
                raise
            if value is None:
                record_miss(namespace)
            else:
                record_hit(namespace)
            return value
        return wrapper
    return deco


# ---------------------------------------------------------------------------
# 与 API key 服务集成 (T1807) — 每次 verify_key 命中/未命中记一次
# ---------------------------------------------------------------------------
def record_api_key_lookup(*, hit: bool, tenant: str) -> None:
    """API key 验证 (DB 命中 vs cache 未命中) — 写入 namespace=api_key.

    生产路径: api_keys 表 → verify_key(plain, record) →
    - hit=True: record.id 找到 + 哈希匹配
    - hit=False: 找不到 / 哈希不匹配 / 已撤销
    """
    ns = f"api_key:{tenant}"
    if hit:
        record_hit(ns)
    else:
        record_miss(ns)


# ---------------------------------------------------------------------------
# 与 webhook dispatcher 集成 (T1807)
# ---------------------------------------------------------------------------
def record_webhook_delivery(*, status: str, tenant: str) -> None:
    """每次 webhook emit 结果记入 namespace=webhook:{tenant}."""
    ns = f"webhook:{tenant}"
    if status == "success":
        record_hit(ns)
    elif status in ("failed_dead_letter", "failed_retrying"):
        record_miss(ns)
    else:
        record_write(ns)


__all__ = [
    "CacheMetrics",
    "CacheStats",
    "get_cache_metrics",
    "record_hit",
    "record_miss",
    "record_eviction",
    "record_write",
    "record_api_key_lookup",
    "record_webhook_delivery",
    "report",
    "track_cache",
]


if __name__ == "__main__":
    # 简单烟囱测试
    for i in range(70):
        record_hit("llm")
    for i in range(30):
        record_miss("llm")
    for i in range(5):
        record_eviction("llm")
    for i in range(120):
        record_api_key_lookup(hit=True, tenant="acme")
    for i in range(30):
        record_api_key_lookup(hit=False, tenant="acme")
    import json
    print(json.dumps(report(), indent=2))