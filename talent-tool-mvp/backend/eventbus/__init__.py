"""Event Bus — public package surface."""

from .base import Event, EventBus, InMemoryEventBus, RedisEventBus, Subscription
from .schema_registry import (
    EventSchema,
    IncompatibleSchemaError,
    SchemaRegistry,
    get_schema_registry,
    set_schema_registry,
)
from .streams import (
    DLQEntry,
    InMemoryStreamBackend,
    StreamEventBus,
    StreamRetryPolicy,
)
from .decorators import (
    await_event,
    clear_registered,
    emit,
    fire,
    listen,
    on_event,
    registered_subscriptions,
)
from .registry import get_event_bus, reset_event_bus, set_event_bus

# v6.0: optional sub-modules
try:
    from .subscribers import register_all_subscribers, SUBSCRIBERS  # noqa: F401
except ImportError:  # pragma: no cover
    register_all_subscribers = None  # type: ignore
    SUBSCRIBERS = []  # type: ignore

try:
    from .integration import (  # noqa: F401
        emit_profile_updated, emit_profile_created, emit_profile_enriched,
        emit_needs_clarified, emit_emotion_detected, emit_emotion_risk,
        emit_plan_generated, emit_market_updated, emit_journal_submitted,
        emit_role_image_updated, emit_strategy_updated,
        emit_ticket_created, emit_ticket_escalated,
        emit_agent_started, emit_agent_completed, emit_agent_failed,
    )
except ImportError:  # pragma: no cover
    pass

__all__ = [
    "Event", "EventBus", "InMemoryEventBus", "RedisEventBus", "Subscription",
    "get_event_bus", "set_event_bus", "reset_event_bus",
    "on_event", "emit", "fire", "listen", "await_event",
    "registered_subscriptions", "clear_registered",
    "register_all_subscribers", "SUBSCRIBERS",
    # v10.0 T5025 — Streams + DLQ + schema registry
    "StreamEventBus", "StreamRetryPolicy", "DLQEntry", "InMemoryStreamBackend",
    "SchemaRegistry", "EventSchema", "IncompatibleSchemaError",
    "get_schema_registry", "set_schema_registry",
]
