"""v10.0 T5026 — Prompt hot reload (no-restart config-driven reload).

Prompts in production evolve continuously (tone tweaks, safety guardrails,
A/B variants). Restarting the process to pick up a new version is unacceptable,
so this module bridges config-center changes to the in-memory
:class:`~services.platform.prompt_v2.PromptService` cache:

1. An operator edits a prompt version in the config center (or calls
   :func:`notify_prompt_changed`).
2. A ``prompt.changed`` event lands on the EventBus.
3. :class:`PromptHotReloader` (subscribed at boot) reloads the affected
   prompt version into the registry and bumps an in-memory ``generation``
   counter so callers can detect the refresh.
4. Every reload is logged + emits an ``agent.prompt.reloaded`` audit-style
   event; failures are isolated (a bad reload never crashes the bus).

The reloader is transport-agnostic: in tests you call ``reload(name)``
directly; in production the EventBus subscriber wires it up automatically.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("waibao.platform.prompt_hot_reload")


@dataclass
class ReloadRecord:
    """A single hot-reload attempt."""

    tenant_id: str
    name: str
    agent: str
    version: int
    success: bool
    error: Optional[str]
    generation: int
    at: float = field(default_factory=time.time)


class PromptHotReloader:
    """Reload prompt versions into the registry without a restart."""

    EVENT_NAME = "prompt.changed"
    RELOADED_EVENT = "agent.prompt.reloaded"

    def __init__(self, service: Any, *, bus: Any = None) -> None:
        self._service = service
        self._bus = bus
        self._lock = threading.RLock()
        self._generation = 0
        self._records: List[ReloadRecord] = []
        self._max_records = 500
        self._subscribed = False
        self._listeners: List[Callable[[ReloadRecord], None]] = []
        # in-memory override store: (tenant, name, agent) -> content
        # When set, ``reload`` updates this and ``get`` serves from it.
        self._overrides: Dict[tuple, str] = {}

    # ---- subscription ---------------------------------------------------
    def start(self) -> None:
        """Subscribe to ``prompt.changed`` events on the bus (idempotent)."""
        if self._subscribed or self._bus is None:
            return
        try:
            self._bus.subscribe(self.EVENT_NAME, self._on_event)
            self._subscribed = True
            logger.info("prompt_hot_reload.subscribed")
        except Exception:  # noqa: BLE001
            logger.exception("prompt_hot_reload.subscribe_failed")

    def stop(self) -> None:
        self._subscribed = False

    def _on_event(self, evt: Any) -> None:
        payload = getattr(evt, "payload", evt) or {}
        self.reload(
            tenant_id=payload.get("tenant_id", "default"),
            name=payload.get("name", ""),
            agent=payload.get("agent", "default"),
            version=payload.get("version"),
            content=payload.get("content"),
        )

    # ---- core -----------------------------------------------------------
    def reload(
        self,
        tenant_id: str,
        name: str,
        agent: str = "default",
        *,
        version: Optional[int] = None,
        content: Optional[str] = None,
    ) -> ReloadRecord:
        """Reload ``name`` for ``(tenant_id, agent)``.

        If ``content`` is provided we upsert a new draft version carrying it
        and activate it. Otherwise we touch the existing version so its cache
        line is invalidated. Bumps ``generation`` on every successful reload.
        """
        with self._lock:
            self._generation += 1
            gen = self._generation
        error: Optional[str] = None
        success = False
        try:
            if content is not None:
                # Hot-reload semantics: the live content changes immediately
                # without forking a new immutable version. We store the override
                # and serve it on the read path; the registry keeps its version
                # history intact. We DO verify the registry is reachable so a
                # broken backend surfaces as a failed reload rather than a
                # silent stale-cache.
                self._service.list_versions(tenant_id, name, agent)
                self._overrides[(tenant_id, name, agent)] = content
            else:
                # invalidate: clear any override for this key
                self._overrides.pop((tenant_id, name, agent), None)
            success = True
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
            logger.exception("prompt_hot_reload.reload_failed name=%s", name)

        record = ReloadRecord(
            tenant_id=tenant_id, name=name, agent=agent,
            version=version or 0, success=success, error=error,
            generation=gen,
        )
        with self._lock:
            self._records.append(record)
            if len(self._records) > self._max_records:
                self._records = self._records[-self._max_records:]
        self._notify(record)
        self._emit_reloaded(record)
        return record

    # ---- read path ------------------------------------------------------
    def get_active_content(self, tenant_id: str, name: str,
                           agent: str = "default") -> Optional[str]:
        """Return the live (possibly hot-reloaded) content for a prompt."""
        override = self._overrides.get((tenant_id, name, agent))
        if override is not None:
            return override
        prompt = self._service.get_active_prompt(tenant_id, name, agent)
        return prompt.content if prompt is not None else None

    @property
    def generation(self) -> int:
        return self._generation

    def records(self) -> List[ReloadRecord]:
        return list(self._records)

    # ---- listeners ------------------------------------------------------
    def add_listener(self, cb: Callable[[ReloadRecord], None]) -> None:
        self._listeners.append(cb)

    def _notify(self, record: ReloadRecord) -> None:
        for cb in list(self._listeners):
            try:
                cb(record)
            except Exception:  # noqa: BLE001
                logger.exception("prompt_hot_reload.listener_failed")

    def _emit_reloaded(self, record: ReloadRecord) -> None:
        if self._bus is None:
            return
        try:
            emit = getattr(self._bus, "emit", None)
            if emit is not None:
                emit(self.RELOADED_EVENT, {
                    "tenant_id": record.tenant_id,
                    "name": record.name,
                    "agent": record.agent,
                    "generation": record.generation,
                    "success": record.success,
                }, source="prompt.hot_reload")
        except Exception:  # noqa: BLE001
            logger.debug("prompt_hot_reload.emit_failed")


# ---------------------------------------------------------------------------
# Programmatic notifier (used by config-center / admin endpoints)
# ---------------------------------------------------------------------------
def notify_prompt_changed(
    bus: Any,
    *,
    tenant_id: str,
    name: str,
    agent: str = "default",
    version: Optional[int] = None,
    content: Optional[str] = None,
) -> None:
    """Publish a ``prompt.changed`` event so every worker's reloader fires."""
    try:
        emit = getattr(bus, "emit", None)
        if emit is None:
            return
        emit(PromptHotReloader.EVENT_NAME, {
            "tenant_id": tenant_id, "name": name, "agent": agent,
            "version": version, "content": content,
        }, source="config.center")
    except Exception:  # noqa: BLE001
        logger.exception("prompt_hot_reload.notify_failed")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_RELOADER: Optional[PromptHotReloader] = None


def get_prompt_reloader(service: Any = None, *, bus: Any = None) -> PromptHotReloader:
    global _RELOADER
    if _RELOADER is None:
        if service is None:
            from .prompt_v2 import get_prompt_service
            service = get_prompt_service()
        if bus is None:
            try:
                from eventbus.registry import get_event_bus
                bus = get_event_bus()
            except Exception:  # noqa: BLE001
                bus = None
        _RELOADER = PromptHotReloader(service, bus=bus)
    return _RELOADER


def reset_prompt_reloader() -> None:
    global _RELOADER
    _RELOADER = None


__all__ = [
    "ReloadRecord",
    "PromptHotReloader",
    "notify_prompt_changed",
    "get_prompt_reloader",
    "reset_prompt_reloader",
]
