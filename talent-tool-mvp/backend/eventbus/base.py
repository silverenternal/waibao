"""Event Bus — v6.0 extensibility abstraction.

Provides a publish/subscribe event bus with both sync and async semantics,
plus in-memory and Redis-backed implementations.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """A domain event flowing through the bus."""
    name: str
    payload: Dict[str, Any]
    source: str = "unknown"
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "payload": self.payload,
            "source": self.source,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "correlation_id": self.correlation_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        return cls(
            name=data["name"],
            payload=data.get("payload", {}),
            source=data.get("source", "unknown"),
            timestamp=data.get("timestamp", time.time()),
            event_id=data.get("event_id") or str(uuid.uuid4()),
            correlation_id=data.get("correlation_id"),
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------

@dataclass
class Subscription:
    """Handle returned to a subscriber, used for unsubscribe."""
    id: str
    event_name: str
    handler: Callable[[Event], Any]
    created_at: float = field(default_factory=time.time)
    is_async: bool = False

    def __repr__(self) -> str:
        return f"Subscription(id={self.id!r}, event={self.event_name!r})"


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class EventBus(ABC):
    """Abstract event bus interface."""

    @abstractmethod
    def publish(self, event: Event) -> None:
        """Publish an event synchronously. Handlers run in the calling thread
        unless the bus itself offloads them."""

    @abstractmethod
    def subscribe(self, event_name: str, handler: Callable[[Event], Any]) -> Subscription:
        """Register a sync handler for an event name. Returns a Subscription."""

    @abstractmethod
    def unsubscribe(self, subscription: Subscription) -> None:
        """Remove a previously registered subscription."""

    @abstractmethod
    def publish_async(self, event: Event) -> Awaitable[None]:
        """Publish an event asynchronously; returns an awaitable that resolves
        when all handlers have completed."""

    # Optional helpers -----------------------------------------------------
    def emit(self, name: str, payload: Optional[Dict[str, Any]] = None,
             source: str = "app", correlation_id: Optional[str] = None) -> Event:
        evt = Event(name=name, payload=payload or {}, source=source,
                    correlation_id=correlation_id)
        self.publish(evt)
        return evt


# ---------------------------------------------------------------------------
# In-memory implementation
# ---------------------------------------------------------------------------

class InMemoryEventBus(EventBus):
    """Default event bus used in dev and tests."""

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Subscription]] = {}
        self._lock = threading.RLock()
        self._errors: List[Dict[str, Any]] = []

    def publish(self, event: Event) -> None:
        with self._lock:
            subs = list(self._handlers.get(event.name, []))
        for sub in subs:
            try:
                sub.handler(event)
            except Exception as exc:  # noqa: BLE001 — isolation
                logger.exception("handler %s failed for %s", sub.id, event.name)
                self._errors.append({"event": event.name, "error": str(exc),
                                     "subscription_id": sub.id})

    def subscribe(self, event_name: str, handler: Callable[[Event], Any]) -> Subscription:
        sub = Subscription(id=str(uuid.uuid4()), event_name=event_name, handler=handler)
        with self._lock:
            self._handlers.setdefault(event_name, []).append(sub)
        return sub

    def unsubscribe(self, subscription: Subscription) -> None:
        with self._lock:
            bucket = self._handlers.get(subscription.event_name, [])
            self._handlers[subscription.event_name] = [
                s for s in bucket if s.id != subscription.id
            ]

    def publish_async(self, event: Event) -> Awaitable[None]:
        async def _run() -> None:
            with self._lock:
                subs = list(self._handlers.get(event.name, []))
            results = await asyncio.gather(
                *(self._invoke(s, event) for s in subs), return_exceptions=True
            )
            for sub, res in zip(subs, results):
                if isinstance(res, Exception):
                    logger.exception("async handler %s failed", sub.id)
                    self._errors.append({"event": event.name, "error": str(res),
                                         "subscription_id": sub.id})

        return _run()

    async def _invoke(self, sub: Subscription, event: Event) -> Any:
        handler = sub.handler
        if inspect.iscoroutinefunction(handler):
            return await handler(event)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, handler, event)

    # Diagnostics ----------------------------------------------------------
    @property
    def errors(self) -> List[Dict[str, Any]]:
        return list(self._errors)

    def clear_errors(self) -> None:
        self._errors.clear()


# ---------------------------------------------------------------------------
# Redis-backed implementation (lazy import for optional dependency)
# ---------------------------------------------------------------------------

class RedisEventBus(EventBus):
    """Redis pub/sub-backed event bus for production multi-process deployments."""

    def __init__(self, url: str = "redis://localhost:6379/0",
                 channel_prefix: str = "waibao:events:") -> None:
        try:
            import redis  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "redis package is required for RedisEventBus — `pip install redis`"
            ) from exc
        self._redis = redis.Redis.from_url(url, decode_responses=True)
        self._prefix = channel_prefix
        self._local = InMemoryEventBus()
        self._pubsub = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # publishing -----------------------------------------------------------
    def publish(self, event: Event) -> None:
        import json
        self._redis.publish(self._prefix + event.name, json.dumps(event.to_dict()))
        # also fan out to local subscribers (same-process shortcuts)
        self._local.publish(event)

    def publish_async(self, event: Event) -> Awaitable[None]:
        return self._local.publish_async(event)

    def subscribe(self, event_name: str, handler: Callable[[Event], Any]) -> Subscription:
        return self._local.subscribe(event_name, handler)

    def unsubscribe(self, subscription: Subscription) -> None:
        self._local.unsubscribe(subscription)

    # background dispatcher ------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="redis-eventbus")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        import json
        ps = self._redis.pubsub(ignore_subscribe_messages=True)
        self._pubsub = ps
        ps.psubscribe(self._prefix + "*")
        for raw in ps.listen():
            if self._stop.is_set():
                break
            if raw is None or raw.get("type") not in ("pmessage", "message"):
                continue
            channel = raw["channel"]
            if isinstance(channel, bytes):
                channel = channel.decode()
            name = channel[len(self._prefix):]
            try:
                evt = Event.from_dict(json.loads(raw["data"]))
                self._local.publish(evt)
            except Exception:
                logger.exception("failed to dispatch redis event %s", name)