"""EventBus subscribers that bridge profile updates into the memory store.

Subscribed events:
  * ``profile.updated``          — write a ``FACT`` memory per changed field
  * ``preference.expressed``     — write a ``PREFERENCE`` memory
  * ``interview.completed``      — write an ``EVENT`` memory
  * ``offer.received``           — write a high-confidence ``EVENT`` memory
  * ``memory.decay.requested``   — trigger periodic decay

Install via ``install_memory_subscribers()`` at app boot.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from eventbus import get_event_bus
from eventbus.base import Event

from .store import MemoryStore, get_memory_store
from .models import MemoryType

logger = logging.getLogger("recruittech.memory.subscribers")


def _resolve_user_id(payload: dict[str, Any]) -> uuid.UUID | None:
    raw = payload.get("user_id") or payload.get("uid")
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except Exception:
        return None


def _resolve_tenant_id(payload: dict[str, Any]) -> uuid.UUID | None:
    raw = payload.get("tenant_id")
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except Exception:
        return None


def _on_profile_updated(evt: Event, store: MemoryStore) -> None:
    payload = evt.payload or {}
    user_id = _resolve_user_id(payload)
    if user_id is None:
        return
    tenant_id = _resolve_tenant_id(payload)
    fields = payload.get("fields") or payload.get("changes") or {}
    if not isinstance(fields, dict) or not fields:
        return
    for key, value in fields.items():
        content = f"{key}: {value}"
        store.add(
            user_id=user_id,
            content=content,
            source_agent="profile.updated",
            type=MemoryType.FACT,
            tenant_id=tenant_id,
            confidence=0.9,
            metadata={"field": key, "event_id": evt.event_id},
        )


def _on_preference_expressed(evt: Event, store: MemoryStore) -> None:
    payload = evt.payload or {}
    user_id = _resolve_user_id(payload)
    if user_id is None:
        return
    tenant_id = _resolve_tenant_id(payload)
    content = payload.get("content") or payload.get("text") or ""
    if not content:
        return
    store.add(
        user_id=user_id,
        content=str(content),
        source_agent="preference.expressed",
        type=MemoryType.PREFERENCE,
        tenant_id=tenant_id,
        confidence=0.8,
        metadata={"event_id": evt.event_id},
    )


def _on_interview_completed(evt: Event, store: MemoryStore) -> None:
    payload = evt.payload or {}
    user_id = _resolve_user_id(payload)
    if user_id is None:
        return
    tenant_id = _resolve_tenant_id(payload)
    role = payload.get("role") or payload.get("job_title") or "interview"
    outcome = payload.get("outcome") or "completed"
    content = f"Interview {outcome} for {role}"
    store.add(
        user_id=user_id,
        content=content,
        source_agent="interview.completed",
        type=MemoryType.EVENT,
        tenant_id=tenant_id,
        confidence=0.95,
        metadata={"event_id": evt.event_id, **payload},
    )


def _on_offer_received(evt: Event, store: MemoryStore) -> None:
    payload = evt.payload or {}
    user_id = _resolve_user_id(payload)
    if user_id is None:
        return
    tenant_id = _resolve_tenant_id(payload)
    company = payload.get("company") or payload.get("employer") or "company"
    role = payload.get("role") or payload.get("title") or "role"
    content = f"Offer received from {company} for {role}"
    store.add(
        user_id=user_id,
        content=content,
        source_agent="offer.received",
        type=MemoryType.EVENT,
        tenant_id=tenant_id,
        confidence=1.0,
        metadata={"event_id": evt.event_id, **payload},
    )


def _on_decay_requested(evt: Event, store: MemoryStore) -> None:
    payload = evt.payload or {}
    factor = float(payload.get("factor", 0.95))
    affected = store.decay(factor)
    logger.info(f"memory decay job ran: affected={affected} factor={factor}")


def install_memory_subscribers(store: MemoryStore | None = None) -> int:
    """Wire memory store into the global EventBus. Idempotent."""
    bus = get_event_bus()
    store = store or get_memory_store()
    bus.subscribe("profile.updated", lambda evt: _on_profile_updated(evt, store))
    bus.subscribe("preference.expressed", lambda evt: _on_preference_expressed(evt, store))
    bus.subscribe("interview.completed", lambda evt: _on_interview_completed(evt, store))
    bus.subscribe("offer.received", lambda evt: _on_offer_received(evt, store))
    bus.subscribe("memory.decay.requested", lambda evt: _on_decay_requested(evt, store))
    logger.info("memory subscribers installed")
    return 5
