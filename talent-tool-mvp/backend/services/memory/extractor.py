"""Entity / fact / preference extraction for T2702.

The extractor pulls a structured list of ``Memory`` candidates from a
chat transcript. It uses the LLM when a client is supplied; otherwise
it falls back to deterministic regex-based heuristics so the test suite
has no external dependencies.

Output is always a list of ``(content, type, confidence)`` tuples — the
caller decides whether to persist them.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Optional

from .models import MemoryType

logger = logging.getLogger("recruittech.memory.extractor")


# ---------------------------------------------------------------------------
# Heuristic patterns
# ---------------------------------------------------------------------------

_PREFERENCE_PATTERNS = [
    re.compile(r"\b(?:i|我)\s*(?:prefer|like|love|enjoy|want|need|希望|想要|喜欢|偏[爱欢好])\s+(.+?)(?:[\.\?\!]|$)", re.IGNORECASE),
    re.compile(r"\b(?:my preference is|我的偏好是)\s+(.+?)(?:[\.\?\!]|$)", re.IGNORECASE),
]

_FACT_PATTERNS = [
    re.compile(r"\b(?:i am|i'm|i work at|i studied|我在|我是|我的专业是|我就职于)\s+(.+?)(?:[\.\?\!]|$)", re.IGNORECASE),
    re.compile(r"\b(?:my (?:name|role|title|skill|experience) is|我的(?:名字|职位|技能|经验)是)\s+(.+?)(?:[\.\?\!]|$)", re.IGNORECASE),
]

_EVENT_PATTERNS = [
    re.compile(r"\b(?:yesterday|today|last week|202\d-\d{2}-\d{2}|昨天|今天|上周)\b.*?([\.\?\!]|$)", re.IGNORECASE),
    re.compile(r"\b(?:interviewed|hired|offer|面试|入职|发了 offer|拿到 offer)\b.*?([\.\?\!]|$)", re.IGNORECASE),
]


class EntityExtractor:
    """Extract memory candidates from a chat transcript.

    ``llm`` is optional. When provided it should expose either:
      * ``chat(messages: list[dict]) -> str``  (sync), or
      * ``async_chat(messages: list[dict]) -> str``

    The extractor never raises: any failure is logged and the
    heuristic extractor is used as a fallback.
    """

    def __init__(self, llm: Any | None = None) -> None:
        self.llm = llm

    def extract(
        self,
        messages: list[dict[str, str]],
        *,
        max_items: int = 16,
    ) -> list[dict[str, Any]]:
        """Return a list of ``{"content": str, "type": MemoryType, "confidence": float}``."""
        out: list[dict[str, Any]] = []
        for m in messages:
            role = (m.get("role") or "").lower()
            content = (m.get("content") or "").strip()
            if not content:
                continue
            if role not in {"user", "human"}:
                # For now we only extract from user turns; assistant turns
                # typically restate user info and would be a dedup concern.
                continue
            out.extend(self._extract_one(content))

        # Deduplicate by lowercased content
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for item in out:
            key = item["content"].strip().lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique[:max_items]

    def _extract_one(self, text: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for pat in _PREFERENCE_PATTERNS:
            for m in pat.finditer(text):
                out.append({
                    "content": m.group(0).strip(),
                    "type": MemoryType.PREFERENCE,
                    "confidence": 0.7,
                })
        for pat in _FACT_PATTERNS:
            for m in pat.finditer(text):
                out.append({
                    "content": m.group(0).strip(),
                    "type": MemoryType.FACT,
                    "confidence": 0.8,
                })
        for pat in _EVENT_PATTERNS:
            for m in pat.finditer(text):
                out.append({
                    "content": m.group(0).strip(),
                    "type": MemoryType.EVENT,
                    "confidence": 0.6,
                })
        return out

    # ---- LLM-backed extraction (optional) ----

    async def extract_async(
        self,
        messages: list[dict[str, str]],
        *,
        max_items: int = 16,
    ) -> list[dict[str, Any]]:
        """Async variant — uses the LLM if available."""
        if self.llm is None:
            return self.extract(messages, max_items=max_items)
        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "You extract atomic memory candidates from a chat. "
                    "Output JSON: "
                    "{\"items\": [{\"content\": str, \"type\": \"fact|preference|event|task\", \"confidence\": 0..1}]}"
                ),
            },
            *messages,
        ]
        try:
            if hasattr(self.llm, "async_chat"):
                raw = await self.llm.async_chat(prompt_messages)
            elif hasattr(self.llm, "chat"):
                raw = self.llm.chat(prompt_messages)
            else:
                return self.extract(messages, max_items=max_items)
        except Exception as e:  # pragma: no cover
            logger.warning(f"LLM extract failed, falling back: {e}")
            return self.extract(messages, max_items=max_items)

        try:
            import json as _json
            data = _json.loads(raw)
            items = data.get("items", []) if isinstance(data, dict) else []
            for it in items:
                it["type"] = MemoryType(it.get("type", "fact"))
                it["confidence"] = float(it.get("confidence", 0.5))
            return items[:max_items]
        except Exception as e:  # pragma: no cover
            logger.warning(f"LLM extract parse failed, falling back: {e}")
            return self.extract(messages, max_items=max_items)
