"""v5.0 services/observability/ public API."""
from __future__ import annotations

from .alerting import (  # noqa: F401,F403
    Alert,
    AlertChannel,
    AlertingService,
    AlertSeverity,
    AlertStatus,
    Channel,
    DEFAULT_ROUTING,
    DingTalkChannel,
    FeishuChannel,
    PagerDutyChannel,
    WebhookChannel,
    fire,
    get_default_service,
    reset_default_service,
)
from .audit import record, audit  # noqa: F401,F403
from .cost_tracker import FLUSH_INTERVAL_SECONDS, BATCH_MAX, CostTrackerService, get_cost_service, reset_cost_service  # noqa: F401,F403
from .llm_budget import LLMBudget  # noqa: F401,F403
from .llm_cache import DEFAULT_TTL_SECONDS, DEFAULT_MAX_SIZE, REDIS_URL, InMemoryBackend, RedisBackend, LLMCache, llm_cache_decorator, get_cache, get_stats, bulk_make_keys  # noqa: F401,F403
from .metrics import init_metrics, is_enabled, get_registry, inc_provider_call, observe_provider_call, inc_ticket_created, inc_match_computed, set_active_users, set_cache_hit_ratio, metrics_asgi_app  # noqa: F401,F403
from .sentry import init_sentry, capture_exception, capture_message  # noqa: F401,F403
from .telemetry import init_telemetry, instrument_app, get_tracer, span  # noqa: F401,F403

__all__: list[str] = [
    # alerting
    "Alert",
    "AlertChannel",
    "AlertingService",
    "AlertSeverity",
    "AlertStatus",
    "Channel",
    "DEFAULT_ROUTING",
    "DingTalkChannel",
    "FeishuChannel",
    "PagerDutyChannel",
    "WebhookChannel",
    "fire",
    "get_default_service",
    "reset_default_service",
    # audit
    "record",
    "audit",
    # cost_tracker
    "FLUSH_INTERVAL_SECONDS",
    "BATCH_MAX",
    "CostTrackerService",
    "get_cost_service",
    "reset_cost_service",
    # llm
    "LLMBudget",
    "DEFAULT_TTL_SECONDS",
    "DEFAULT_MAX_SIZE",
    "REDIS_URL",
    "InMemoryBackend",
    "RedisBackend",
    "LLMCache",
    "llm_cache_decorator",
    "get_cache",
    "get_stats",
    "bulk_make_keys",
    # metrics
    "init_metrics",
    "is_enabled",
    "get_registry",
    "inc_provider_call",
    "observe_provider_call",
    "inc_ticket_created",
    "inc_match_computed",
    "set_active_users",
    "set_cache_hit_ratio",
    "metrics_asgi_app",
    # sentry
    "init_sentry",
    "capture_exception",
    "capture_message",
    # telemetry
    "init_telemetry",
    "instrument_app",
    "get_tracer",
    "span",
]
