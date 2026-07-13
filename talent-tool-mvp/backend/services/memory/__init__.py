"""T2702: Agent 统一记忆库 (Mem0 vendor-in).

Public API:
  * Memory, MemoryType, MemoryLink          - data models
  * MemoryStore                              - vendor Mem0 client wrapper
  * get_memory_store / reset_memory_store    - singleton access
  * EntityExtractor                          - LLM 实体/fact/preference/event 抽取
  * MemoryInjector                           - context 注入 helpers (for agent run())
  * memory_event_handler                     - profile.updated -> auto write
"""
from __future__ import annotations

from .extractor import EntityExtractor
from .injector import MemoryInjector
from .models import (
    Memory,
    MemoryLink,
    MemoryQuery,
    MemoryType,
    RelationType,
)
from .store import (
    MemoryStore,
    MemoryStoreError,
    get_memory_store,
    reset_memory_store,
)
from .subscribers import install_memory_subscribers

__all__ = [
    "Memory",
    "MemoryLink",
    "MemoryQuery",
    "MemoryType",
    "RelationType",
    "MemoryStore",
    "MemoryStoreError",
    "get_memory_store",
    "reset_memory_store",
    "EntityExtractor",
    "MemoryInjector",
    "install_memory_subscribers",
]
