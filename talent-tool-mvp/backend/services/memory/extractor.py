"""Entity / fact / preference extraction — T5021 real LLM extractor.

The primary path is a **real LLM** call that returns atomic memory
candidates as structured JSON.  The legacy regex heuristics are retained
*only* as an explicit ``heuristic`` fallback used when:

  * no ``llm`` client is wired, or
  * the caller passes ``strategy="heuristic"`` (tests / offline).

Production callers MUST pass an ``llm`` client and call ``extract_async``
— ``extract`` (sync, heuristic) is kept for compatibility but logs a
warning when used without an LLM.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterable

from .models import MemoryType

logger = logging.getLogger("waibao.memory.extractor")


# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a memory extraction engine for a recruitment copilot. "
    "Read the conversation and extract ATOMIC, self-contained memory "
    "candidates about the user. Each candidate must be a single fact, "
    "preference, event, or task — never a compound sentence.\n\n"
    "Classify each candidate:\n"
    "  - fact        : an objective statement ('works at Acme as Staff Engineer')\n"
    "  - preference  : a like/want/need ('prefers fully remote roles')\n"
    "  - event       : something that happened ('interviewed at Globex on 2026-06-01')\n"
    "  - task        : an open todo / follow-up ('send offer letter by Friday')\n"
    "  - summary     : a higher-level synthesis of the session\n\n"
    "Output STRICT JSON only:\n"
    '{"items": [{"content": str, "type": "fact|preference|event|task|summary", '
    '"confidence": 0.0..1.0, "entities": {"org": [...], "skill": [...], "date": [...]}}]}\n\n'
    "Omit items you are not at least 0.4 confident about."
)


# ---------------------------------------------------------------------------
# Heuristic fallback (offline / tests)
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


def _heuristic_extract_one(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pat in _PREFERENCE_PATTERNS:
        for m in pat.finditer(text):
            out.append({"content": m.group(0).strip(), "type": MemoryType.PREFERENCE, "confidence": 0.7})
    for pat in _FACT_PATTERNS:
        for m in pat.finditer(text):
            out.append({"content": m.group(0).strip(), "type": MemoryType.FACT, "confidence": 0.8})
    for pat in _EVENT_PATTERNS:
        for m in pat.finditer(text):
            out.append({"content": m.group(0).strip(), "type": MemoryType.EVENT, "confidence": 0.6})
    return out


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class EntityExtractor:
    """Extract memory candidates from a chat transcript.

    ``llm`` is the real backend. It should expose either:
      * ``async_chat(messages) -> str`` (preferred), or
      * ``chat(messages) -> str`` (sync).

    When no ``llm`` is supplied, the heuristic extractor is used and a
    warning is logged. Pass ``strategy="heuristic"`` to silence the
    warning in tests.
    """

    def __init__(self, llm: Any | None = None, *, strategy: str = "auto") -> None:
        self.llm = llm
        self.strategy = strategy

    # ------------------------------------------------------------------
    # Sync (heuristic-only) — kept for backwards compatibility
    # ------------------------------------------------------------------
    def extract(
        self,
        messages: list[dict[str, str]],
        *,
        max_items: int = 16,
    ) -> list[dict[str, Any]]:
        if self.llm is not None and self.strategy != "heuristic":
            logger.info("sync extract() ignores the LLM; call extract_async() for real extraction")
        out: list[dict[str, Any]] = []
        for m in messages:
            role = (m.get("role") or "").lower()
            content = (m.get("content") or "").strip()
            if not content or role not in {"user", "human"}:
                continue
            out.extend(_heuristic_extract_one(content))

        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for item in out:
            key = item["content"].strip().lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique[:max_items]

    # ------------------------------------------------------------------
    # Async (real LLM) — primary production path
    # ------------------------------------------------------------------
    async def extract_async(
        self,
        messages: list[dict[str, str]],
        *,
        max_items: int = 16,
    ) -> list[dict[str, Any]]:
        if self.llm is None or self.strategy == "heuristic":
            if self.llm is None and self.strategy == "auto":
                logger.warning("no LLM wired — falling back to heuristic extraction")
            return self.extract(messages, max_items=max_items)

        prompt_messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            *_normalize_messages(messages),
        ]
        try:
            if hasattr(self.llm, "async_chat"):
                raw = await self.llm.async_chat(prompt_messages)
            elif hasattr(self.llm, "chat"):
                raw = self.llm.chat(prompt_messages)
            else:
                logger.warning("llm has no chat/async_chat — heuristic fallback")
                return self.extract(messages, max_items=max_items)
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM extract failed, falling back: %s", e)
            return self.extract(messages, max_items=max_items)

        items = self._parse(raw, max_items)
        if not items and self.strategy == "auto":
            # The model produced nothing parseable — degrade gracefully.
            logger.warning("LLM returned no parseable items — heuristic fallback")
            return self.extract(messages, max_items=max_items)
        return items

    # ------------------------------------------------------------------
    def _parse(self, raw: str, max_items: int) -> list[dict[str, Any]]:
        try:
            data = json.loads(_extract_json(raw))
        except Exception:  # noqa: BLE001
            return []
        rows = data.get("items", []) if isinstance(data, dict) else []
        out: list[dict[str, Any]] = []
        for it in rows:
            if not isinstance(it, dict):
                continue
            content = (it.get("content") or "").strip()
            if not content:
                continue
            try:
                mtype = MemoryType(it.get("type", "fact"))
            except ValueError:
                mtype = MemoryType.FACT
            conf = float(it.get("confidence", 0.5))
            conf = max(0.0, min(1.0, conf))
            item: dict[str, Any] = {
                "content": content,
                "type": mtype,
                "confidence": conf,
            }
            if isinstance(it.get("entities"), dict):
                item["entities"] = it["entities"]
            out.append(item)
        return out[:max_items]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    norm: list[dict[str, str]] = []
    for m in messages:
        role = (m.get("role") or "user").lower()
        content = (m.get("content") or "").strip()
        if not content:
            continue
        norm.append({"role": role, "content": content})
    return norm


def _extract_json(raw: str) -> str:
    """Pull the first JSON object out of an LLM response that may include
    prose / markdown fences."""
    raw = raw.strip()
    if raw.startswith("```"):
        # strip markdown fences
        raw = raw.strip("`")
        # remove a leading language tag like 'json'
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw[start : end + 1]
    return raw
