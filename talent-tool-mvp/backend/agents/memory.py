"""三层记忆系统.

- 短期记忆 (short_term): 单次对话上下文,存在进程内存
- 工作记忆 (working): 当前任务工作区,跨调用保留,Redis
- 长期记忆 (long_term): 用户画像/历史偏好,Supabase memory 表
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Optional

from supabase import Client

from agents.runtime import MemoryScope

logger = logging.getLogger("recruittech.agents.memory")


class MemoryStore:
    """统一记忆存储接口."""

    async def write(self, scope: MemoryScope, user_id: str, key: str, value: Any): ...
    async def read(self, scope: MemoryScope, user_id: str, key: str, default: Any = None) -> Any: ...
    async def delete(self, scope: MemoryScope, user_id: str, key: str): ...
    async def list_keys(self, scope: MemoryScope, user_id: str, prefix: str = "") -> list[str]: ...


class InMemoryStore(MemoryStore):
    """进程内短期记忆(单实例)."""

    def __init__(self, ttl_seconds: int = 3600):
        self._store: dict[tuple[str, str, str], tuple[Any, float]] = {}
        self.ttl = ttl_seconds

    async def write(self, scope, user_id, key, value):
        if scope == MemoryScope.long_term:
            return  # 短期 store 不持久化 long_term
        self._store[(scope.value, user_id, key)] = (value, time.time() + self.ttl)

    async def read(self, scope, user_id, key, default=None):
        entry = self._store.get((scope.value, user_id, key))
        if not entry:
            return default
        value, exp = entry
        if time.time() > exp:
            del self._store[(scope.value, user_id, key)]
            return default
        return value

    async def delete(self, scope, user_id, key):
        self._store.pop((scope.value, user_id, key), None)

    async def list_keys(self, scope, user_id, prefix=""):
        return [
            k for (s, u, k) in self._store
            if s == scope.value and u == user_id and k.startswith(prefix)
        ]


class SupabaseMemoryStore(MemoryStore):
    """基于 agent_memory 表的长期记忆."""

    def __init__(self, supabase: Client):
        self.supabase = supabase

    async def write(self, scope, user_id, key, value):
        record = {
            "user_id": user_id,
            "scope": scope.value,
            "key": key,
            "value": value if isinstance(value, (str, int, float, bool, list, dict)) else str(value),
            "updated_at": "now()",
        }
        self.supabase.table("agent_memory").upsert(
            record, on_conflict="user_id,scope,key"
        ).execute()

    async def read(self, scope, user_id, key, default=None):
        result = (
            self.supabase.table("agent_memory")
            .select("value")
            .eq("user_id", user_id)
            .eq("scope", scope.value)
            .eq("key", key)
            .maybe_single()
            .execute()
        )
        return result.data.get("value") if result and result.data else default

    async def delete(self, scope, user_id, key):
        self.supabase.table("agent_memory").delete().eq(
            "user_id", user_id
        ).eq("scope", scope.value).eq("key", key).execute()

    async def list_keys(self, scope, user_id, prefix=""):
        result = (
            self.supabase.table("agent_memory")
            .select("key")
            .eq("user_id", user_id)
            .eq("scope", scope.value)
            .like("key", f"{prefix}%")
            .execute()
        )
        return [r["key"] for r in (result.data or [])]


class CompositeMemory(MemoryStore):
    """组合: 短期内存 + 长期 Supabase."""

    def __init__(self, supabase: Optional[Client] = None):
        self.short = InMemoryStore()
        self.long = SupabaseMemoryStore(supabase) if supabase else None

    async def write(self, scope, user_id, key, value):
        await self.short.write(scope, user_id, key, value)
        if scope == MemoryScope.long_term and self.long:
            await self.long.write(scope, user_id, key, value)

    async def read(self, scope, user_id, key, default=None):
        v = await self.short.read(scope, user_id, key, default=None)
        if v is not None:
            return v
        if self.long:
            return await self.long.read(scope, user_id, key, default=default)
        return default

    async def delete(self, scope, user_id, key):
        await self.short.delete(scope, user_id, key)
        if self.long:
            await self.long.delete(scope, user_id, key)

    async def list_keys(self, scope, user_id, prefix=""):
        keys = await self.short.list_keys(scope, user_id, prefix)
        if self.long and scope == MemoryScope.long_term:
            keys = list(set(keys + await self.long.list_keys(scope, user_id, prefix)))
        return keys