"""Context injection helpers for T2702.

The ``MemoryInjector`` is called by every agent right before the LLM
is invoked. It pulls the user's top-K relevant memories, formats them
as a system-prompt section, and returns the augmented prompt list.

The injector is intentionally side-effect-free: it does not write any
memories.  Writes are an explicit agent action.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Iterable, Optional

from .models import Memory, MemoryType
from .store import MemoryStore, get_memory_store

logger = logging.getLogger("recruittech.memory.injector")


class MemoryInjector:
    """Format & inject memory context into agent prompts."""

    def __init__(self, store: Optional[MemoryStore] = None, *, max_items: int = 8) -> None:
        self.store = store or get_memory_store()
        self.max_items = max_items

    def build_context_block(
        self,
        *,
        user_id: uuid.UUID,
        query_text: str,
        types: Optional[list[MemoryType | str]] = None,
        top_k: int = 8,
    ) -> str:
        """Return a plain-text block suitable for splicing into a system prompt."""
        memories = self.store.query(
            user_id=user_id,
            query_text=query_text,
            top_k=top_k or self.max_items,
            types=types,
        )
        if not memories:
            return ""
        lines = ["[MEMORY CONTEXT — relevant past interactions]"]
        for m in memories:
            tag = m.type.value.upper()
            conf = f"{m.confidence:.2f}"
            decay = f"{m.decay_score:.2f}"
            line = f"- ({tag}, conf={conf}, decay={decay}, agent={m.source_agent}) {m.content}"
            lines.append(line)
        lines.append("[END MEMORY CONTEXT]")
        return "\n".join(lines)

    def inject(
        self,
        messages: list[dict[str, str]],
        *,
        user_id: uuid.UUID,
        query_text: str,
        types: Optional[list[MemoryType | str]] = None,
        top_k: int = 8,
    ) -> list[dict[str, str]]:
        """Return a *new* messages list with the memory block prepended to the system message."""
        block = self.build_context_block(
            user_id=user_id, query_text=query_text, types=types, top_k=top_k
        )
        if not block:
            return messages
        out: list[dict[str, str]] = []
        injected = False
        for m in messages:
            if (m.get("role") or "").lower() == "system" and not injected:
                out.append({
                    "role": "system",
                    "content": (m.get("content") or "") + "\n\n" + block,
                })
                injected = True
            else:
                out.append(m)
        if not injected:
            out.insert(0, {"role": "system", "content": block})
        return out
