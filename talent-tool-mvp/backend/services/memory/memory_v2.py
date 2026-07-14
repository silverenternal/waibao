"""v10.0 T5029 — profile_updated → Mem0 merge + agent context auto-sync.

When a jobseeker's profile changes (an agent emits ``profile.updated``), the
delta must land in the unified memory store **merged** with what we already
know — not as a stream of near-duplicate facts. This module provides:

* :class:`ProfileMemoryMerger` — subscribes to ``profile.updated`` events,
  coerces each changed field into a canonical ``FACT`` memory, and **merges**
  it with an existing memory for the same field (updating the value + bumping
  confidence) instead of inserting a duplicate. Conflicting old values are
  superseded but retained as metadata for audit.
* :meth:`sync_agent_context` — pulls the merged profile facts back into a
  system-prompt block so the next agent invocation sees the up-to-date
  profile without an explicit reload.

It is transport-agnostic: tests call :meth:`apply_update` directly; in
production the EventBus subscriber wires it up.
"""
from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, Dict, List, Optional

from services.memory.models import Memory, MemoryType
from services.memory.store import MemoryStore, get_memory_store

logger = logging.getLogger("recruittech.memory.v2")


# Fields we treat as "profile facts" worth persisting. Anything else is
# dropped (profile.updated carries a lot of transient metadata).
PROFILE_FIELDS = {
    "name", "full_name", "email", "phone", "location", "city",
    "current_role", "current_title", "seniority", "years_experience",
    "skills", "industry", "education", "languages", "availability",
    "preferred_location", "salary_expectation", "work_mode",
}


class ProfileMemoryMerger:
    """Merge profile.updated deltas into the Mem0 store, deduplicating by field.

    Each field becomes one ``FACT`` memory keyed by the tuple
    ``(user_id, "profile", field_name)``. Re-applying the same field updates
    the existing memory's content + confidence and records the prior value in
    ``metadata.prior_values`` (capped) so the change is auditable.
    """

    EVENT_NAME = "profile.updated"

    def __init__(self, store: Optional[MemoryStore] = None) -> None:
        self.store = store or get_memory_store()
        self._lock = threading.RLock()
        self._index: Dict[tuple, uuid.UUID] = {}  # (user, field) -> memory_id
        self._subscribed = False

    # ---- subscription ---------------------------------------------------
    def start(self, bus: Any = None) -> None:
        if self._subscribed:
            return
        if bus is None:
            try:
                from eventbus.registry import get_event_bus
                bus = get_event_bus()
            except Exception:  # noqa: BLE001
                bus = None
        if bus is None:
            return
        try:
            bus.subscribe(self.EVENT_NAME, self._on_event)
            self._subscribed = True
        except Exception:  # noqa: BLE001
            logger.exception("profile_memory_merger.subscribe_failed")

    def _on_event(self, evt: Any) -> None:
        payload = getattr(evt, "payload", evt) or {}
        user_id = payload.get("user_id")
        if user_id is None:
            return
        try:
            user_uuid = uuid.UUID(str(user_id))
        except (TypeError, ValueError):
            return
        fields = payload.get("fields") or {}
        tenant_id = payload.get("tenant_id")
        self.apply_update(
            user_id=user_uuid,
            fields=fields if isinstance(fields, dict) else {},
            tenant_id=_to_uuid(tenant_id),
        )

    # ---- core -----------------------------------------------------------
    def apply_update(
        self,
        *,
        user_id: uuid.UUID,
        fields: Dict[str, Any],
        tenant_id: Optional[uuid.UUID] = None,
        source_agent: str = "profile_agent",
        confidence: float = 0.95,
    ) -> List[Memory]:
        """Merge ``fields`` into memory. Returns the memories touched."""
        touched: List[Memory] = []
        if not fields:
            return touched
        with self._lock:
            for field, value in fields.items():
                if field not in PROFILE_FIELDS:
                    continue
                if value is None or value == "":
                    continue
                memory = self._upsert_field(
                    user_id=user_id, field=field, value=value,
                    tenant_id=tenant_id, source_agent=source_agent,
                    confidence=confidence,
                )
                if memory is not None:
                    touched.append(memory)
        return touched

    def _upsert_field(
        self,
        *,
        user_id: uuid.UUID,
        field: str,
        value: Any,
        tenant_id: Optional[uuid.UUID],
        source_agent: str,
        confidence: float,
    ) -> Optional[Memory]:
        key = (user_id, field)
        existing_id = self._index.get(key)
        content = f"profile.{field} = {_render(value)}"

        # If we already have this exact value, no-op.
        if existing_id is not None:
            existing = self._find_memory(existing_id, user_id)
            if existing is not None and existing.content == content:
                return existing

        if existing_id is None:
            # search the store for an existing profile fact for this field
            existing = self._find_field_fact(user_id, field)
            if existing is not None:
                existing_id = existing.id
                self._index[key] = existing_id

        if existing_id is not None:
            existing = self._find_memory(existing_id, user_id)
            if existing is not None:
                return self._merge_into(existing, field, value, content,
                                         source_agent, confidence)

        # brand new memory
        mem = self.store.add(
            user_id=user_id, content=content, source_agent=source_agent,
            type=MemoryType.FACT, tenant_id=tenant_id, confidence=confidence,
            metadata={"profile_field": field, "profile_value": _render(value)},
        )
        self._index[key] = mem.id
        return mem

    def _merge_into(
        self, existing: Memory, field: str, value: Any, content: str,
        source_agent: str, confidence: float,
    ) -> Memory:
        prior = existing.metadata.get("profile_value")
        prior_values = list(existing.metadata.get("prior_values", []))
        if prior is not None and prior != _render(value):
            prior_values.append(prior)
            prior_values = prior_values[-10:]  # cap history
        # Mem0 semantics: update content + confidence + metadata in place.
        existing.content = content
        existing.confidence = max(existing.confidence, confidence)
        meta = dict(existing.metadata or {})
        meta["profile_field"] = field
        meta["profile_value"] = _render(value)
        meta["prior_values"] = prior_values
        meta["last_updated_by"] = source_agent
        existing.metadata = meta
        # persist the mutation through the backend if it supports updates
        try:
            self.store.backend.update(existing)  # type: ignore[attr-defined]
        except AttributeError:
            try:
                # fallback: re-insert so the change is durable
                self.store.backend.insert(existing)
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            logger.exception("profile_memory_merger.update_failed field=%s", field)
        return existing

    def _find_memory(self, memory_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Memory]:
        try:
            backend = self.store.backend
            mems = backend.search(user_id, "", top_k=500) if hasattr(backend, "search") else []
            for mem, _score in (mems or []):
                if mem.id == memory_id:
                    return mem
        except Exception:  # noqa: BLE001
            pass
        return None

    def _find_field_fact(self, user_id: uuid.UUID, field: str) -> Optional[Memory]:
        try:
            backend = self.store.backend
            mems = backend.search(user_id, f"profile.{field}", top_k=50,
                                    types=[MemoryType.FACT]) \
                if hasattr(backend, "search") else []
        except Exception:  # noqa: BLE001
            mems = []
        for mem, _score in (mems or []):
            if mem.metadata.get("profile_field") == field:
                return mem
        return None

    # ---- read path ------------------------------------------------------
    def profile_facts(self, user_id: uuid.UUID) -> List[Memory]:
        """Return all profile-field facts known for ``user_id``."""
        mems = self.store.query(user_id=user_id, query_text="profile",
                                 top_k=50, types=[MemoryType.FACT])
        return [m for m in mems if m.metadata.get("profile_field")]

    def sync_agent_context(
        self, user_id: uuid.UUID, *, query_text: str = "profile",
    ) -> str:
        """Build a system-prompt block from the merged profile facts."""
        facts = self.profile_facts(user_id)
        if not facts:
            return ""
        lines = ["[PROFILE — merged from profile.updated events]"]
        for fact in sorted(facts, key=lambda m: m.metadata.get("profile_field", "")):
            field = fact.metadata.get("profile_field", "unknown")
            value = fact.metadata.get("profile_value", "")
            lines.append(f"- {field}: {value}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _render(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    return str(value)


def _to_uuid(value: Any) -> Optional[uuid.UUID]:
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_MERGER: Optional[ProfileMemoryMerger] = None


def get_profile_memory_merger(store: Optional[MemoryStore] = None) -> ProfileMemoryMerger:
    global _MERGER
    if _MERGER is None:
        _MERGER = ProfileMemoryMerger(store=store)
    return _MERGER


def reset_profile_memory_merger() -> None:
    global _MERGER
    _MERGER = None


__all__ = [
    "ProfileMemoryMerger",
    "PROFILE_FIELDS",
    "get_profile_memory_merger",
    "reset_profile_memory_merger",
]
