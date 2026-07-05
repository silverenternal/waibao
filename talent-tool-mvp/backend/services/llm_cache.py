"""LLM 调用缓存 — T402.

对相同 prompt+response_format 启用 Redis/Memory 缓存.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger("recruittech.services.llm_cache")


class LLMCache:
    """简易 LLM 调用缓存(内存版,生产可换 Redis)."""

    def __init__(self, ttl_seconds: int = 3600, max_size: int = 1000):
        self._store: dict[str, tuple[Any, float]] = {}
        self.ttl = ttl_seconds
        self.max_size = max_size

    @staticmethod
    def _key(messages: list[dict], model: str, **kwargs) -> str:
        h = hashlib.md5()
        h.update(model.encode())
        h.update(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode())
        h.update(json.dumps(kwargs, sort_keys=True).encode())
        return h.hexdigest()

    def get(self, messages: list[dict], model: str, **kwargs) -> Optional[Any]:
        key = self._key(messages, model, **kwargs)
        entry = self._store.get(key)
        if not entry:
            return None
        value, exp = entry
        if time.time() > exp:
            del self._store[key]
            return None
        return value

    def set(self, messages: list[dict], model: str, value: Any, **kwargs):
        if len(self._store) >= self.max_size:
            # LRU 简化: 删最早插入的
            oldest = next(iter(self._store))
            del self._store[oldest]
        key = self._key(messages, model, **kwargs)
        self._store[key] = (value, time.time() + self.ttl)

    def stats(self) -> dict:
        return {
            "size": len(self._store),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl,
        }


# 全局实例
llm_cache = LLMCache()