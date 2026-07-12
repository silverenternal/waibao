"""Global EventBus registry.

Most of the codebase should not pick its own bus instance — it should call
``get_event_bus()`` and rely on the bootstrap phase to install the right
implementation (InMemory in dev/test, Redis in prod).
"""

from __future__ import annotations

import os
import threading
from typing import Optional

from .base import EventBus, InMemoryEventBus

_lock = threading.RLock()
_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Return the process-wide EventBus, lazily installing the default."""
    global _bus
    with _lock:
        if _bus is None:
            kind = os.getenv("WAIBAO_EVENTBUS", "memory").lower()
            if kind == "redis":
                from .base import RedisEventBus  # local import — optional dep
                _bus = RedisEventBus(url=os.getenv("WAIBAO_REDIS_URL",
                                                  "redis://localhost:6379/0"))
            else:
                _bus = InMemoryEventBus()
        return _bus


def set_event_bus(bus: EventBus) -> None:
    """Install a specific EventBus (mainly used by tests)."""
    global _bus
    with _lock:
        _bus = bus


def reset_event_bus() -> None:
    """Clear the cached bus — only used in test fixtures."""
    global _bus
    with _lock:
        _bus = None


__all__ = ["get_event_bus", "set_event_bus", "reset_event_bus"]