"""Decorators and ergonomic helpers for working with the EventBus.

The goal is that any module can subscribe / publish without manually
managing Subscription handles:

    from backend.eventbus import on_event, emit

    @on_event("clarifier.completed")
    def _on_done(evt: Event) -> None:
        ...

    emit("user.created", {"id": 42})
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from typing import Any, Callable, List

from .base import Event, EventBus, Subscription
from .registry import get_event_bus

# ---------------------------------------------------------------------------
# @on_event decorator
# ---------------------------------------------------------------------------

# Module-level registry of (subscription_id, handler) so that we can
# expose them in tooling (e.g. an admin endpoint listing subscribers).
_REGISTERED: List[Subscription] = []


def on_event(event_name: str, *, bus: EventBus | None = None) -> Callable[[Callable], Callable]:
    """Register a function as a handler for an event name.

    Works for both sync and async handlers.
    """

    def decorator(func: Callable) -> Callable:
        target = bus or get_event_bus()
        sub = target.subscribe(event_name, func)
        sub.is_async = inspect.iscoroutinefunction(func)
        _REGISTERED.append(sub)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        wrapper.__waibao_subscription__ = sub  # type: ignore[attr-defined]
        return wrapper

    return decorator


def registered_subscriptions() -> List[Subscription]:
    """Return all subscriptions registered via @on_event."""
    return list(_REGISTERED)


def clear_registered() -> None:
    """Detach every @on_event handler. Mainly used in tests."""
    bus = get_event_bus()
    for sub in _REGISTERED:
        bus.unsubscribe(sub)
    _REGISTERED.clear()


# ---------------------------------------------------------------------------
# Ergonomic aliases (used by agents in v6+)
# ---------------------------------------------------------------------------

def emit(name: str, payload: dict | None = None, *,
         source: str = "app", correlation_id: str | None = None,
         bus: EventBus | None = None) -> Event:
    """Publish an event. Returns the Event for chaining/tests."""
    return (bus or get_event_bus()).emit(name, payload, source=source,
                                          correlation_id=correlation_id)


def fire(name: str, **payload: Any) -> Event:
    """Sugar over emit(): keyword arguments become the payload dict."""
    return emit(name, payload)


def listen(event_name: str, handler: Callable[[Event], Any], *,
           bus: EventBus | None = None) -> Subscription:
    """Programmatic subscribe that returns the Subscription."""
    return (bus or get_event_bus()).subscribe(event_name, handler)


async def await_event(event_name: str, *, timeout: float | None = None,
                      bus: EventBus | None = None) -> Event | None:
    """Resolve with the next event matching `event_name`.

    Returns ``None`` if ``timeout`` elapses without an event.
    """
    target = bus or get_event_bus()
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[Event] = loop.create_future()

    def _handler(evt: Event) -> None:
        if not fut.done():
            fut.set_result(evt)

    sub = target.subscribe(event_name, _handler)
    try:
        if timeout is None:
            return await fut
        return await asyncio.wait_for(fut, timeout=timeout)
    except (asyncio.TimeoutError, TimeoutError):
        return None
    finally:
        target.unsubscribe(sub)


def is_async_handler(func: Callable) -> bool:
    return inspect.iscoroutinefunction(func)