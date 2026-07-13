"""T2702 — Agent 适配器.

Wraps the existing ``BaseAgent.run()`` flow so that every agent:

  1.  Queries the unified memory store for relevant context
  2.  Injects that context into the system prompt
  3.  Lets ``_handle()`` run as before
  4.  Persists any ``memory_writes`` to the unified store (with the
      correct ``source_agent``) — in addition to the legacy kv memory
  5.  Returns the augmented ``AgentOutput`` (so callers see the
      context block in ``artifacts``).

The adapter is intentionally a thin shim.  Existing agents can opt in
by constructing ``MemoryAwareAgent(agent, memory_store)`` instead of
calling ``agent.run()`` directly.  A standalone ``memory_aware_run()``
helper is also exposed for callers that don't want to wrap.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Optional

from .injector import MemoryInjector
from .store import MemoryStore, get_memory_store
from .models import MemoryType

logger = logging.getLogger("recruittech.memory.agent_adapter")


def _coerce_uuid(raw: Any) -> uuid.UUID | None:
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw))
    except Exception:
        return None


async def memory_aware_run(
    agent: Any,
    agent_input: Any,
    *,
    store: MemoryStore | None = None,
    injector: MemoryInjector | None = None,
    inject_types: list[MemoryType] | None = None,
) -> Any:
    """Run an agent with unified memory injection.

    ``agent`` must be a ``BaseAgent`` (have a ``run(AgentInput)`` method).
    ``agent_input`` is the standard ``AgentInput`` dataclass.
    """
    store = store or get_memory_store()
    injector = injector or MemoryInjector(store)

    user_uuid = _coerce_uuid(agent_input.user_id) or uuid.uuid4()

    # 1) Build context block (best-effort — never crash the run)
    try:
        block = injector.build_context_block(
            user_id=user_uuid,
            query_text=agent_input.text,
            types=inject_types,
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"memory_aware_run: build_context_block failed: {e}")
        block = ""

    if block:
        ctx = dict(agent_input.context or {})
        ctx["memory_context"] = block
        agent_input.context = ctx

    # 2) Run the agent
    output = await agent.run(agent_input)

    # 3) Translate legacy memory_writes into unified memories
    if output.memory_writes:
        tenant_uuid = _coerce_uuid(
            (agent_input.context or {}).get("tenant_id")
        ) or uuid.UUID(int=0)
        for w in output.memory_writes:
            content = w.get("content")
            if not content:
                content = f"{w.get('key','')}: {w.get('value','')}"
            try:
                store.add(
                    user_id=user_uuid,
                    content=str(content),
                    source_agent=agent.name,
                    type=MemoryType.FACT,
                    tenant_id=tenant_uuid,
                    confidence=float(w.get("confidence", 0.8)),
                    metadata={
                        "legacy_key": w.get("key"),
                        "scope": w.get("scope", "working"),
                    },
                )
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(
                    f"memory_aware_run: failed to persist memory write: {e}"
                )

    # 4) Stash the block in artifacts so callers can inspect what was injected
    if block:
        artifacts = dict(output.artifacts or {})
        artifacts.setdefault("memory_context", block[:1024])
        output.artifacts = artifacts

    return output


class MemoryAwareAgent:
    """A small wrapper that exposes the same ``run()`` interface.

    Usage:
        base = ProfileAgent(llm=llm, memory=memory)
        agent = MemoryAwareAgent(base)
        out = await agent.run(agent_input)
    """

    def __init__(
        self,
        base_agent: Any,
        *,
        store: MemoryStore | None = None,
        injector: MemoryInjector | None = None,
        inject_types: list[MemoryType] | None = None,
    ) -> None:
        self._base = base_agent
        self._store = store
        self._injector = injector
        self._inject_types = inject_types

    @property
    def base(self) -> Any:
        return self._base

    def __getattr__(self, item: str) -> Any:
        return getattr(self._base, item)

    async def run(self, agent_input: Any) -> Any:
        return await memory_aware_run(
            self._base,
            agent_input,
            store=self._store,
            injector=self._injector,
            inject_types=self._inject_types,
        )
