"""v8.0 T3501 / v10.0 T5002 — Service Toggle (split package).

The service was a single 792-line module in v8.0; v10.0 T5002 splits it into
three cohesive submodules while keeping the public surface 100 % backward
compatible:

    registry     — register / deregister / catalog read paths
    gate         — multi-layer access checks (status + plan + role + override)
    dependency   — cross-service dependency graph (disable guards / rollback)

All logic lives in :mod:`._core`; the submodules re-export the relevant slice
of the API.  ``service_toggle`` (the singleton) and every previously-importable
name remain available here so existing ``from services.platform.service_toggle
import service_toggle`` and ``import ...service_toggle as st`` keep working.
"""
from __future__ import annotations

# Re-export everything from the core so the package surface is identical to the
# pre-split flat module.  Private names are re-exported on purpose because the
# pre-split module exposed them as module attributes and tests / monkeypatching
# fixtures rely on ``service_toggle._supabase`` / ``service_toggle._LOCAL_CACHE``
# being writable through the package object.
from ._core import (  # noqa: F401
    CACHE_TTL_SECONDS,
    DependencyError,
    ServiceNotFoundError,
    ServiceToggle,
    ServiceToggleError,
    invalidate_cache,
    service_toggle,
)
# Module-level internals the tests monkeypatch directly on the module object.
from ._core import (  # noqa: F401
    _LOCAL_CACHE,
    _LOCAL_TS,
    _cache_get,
    _cache_set,
    _emit,
    _get_redis,
    _key_catalog,
    _key_override,
    _key_service,
    _now_iso,
    _supabase,
    _supabase_safe,
)
from .dependency import *  # noqa: F401,F403
from .gate import *  # noqa: F401,F403
from .registry import *  # noqa: F401,F403

__all__ = [
    "CACHE_TTL_SECONDS",
    "DependencyError",
    "ServiceNotFoundError",
    "ServiceToggle",
    "ServiceToggleError",
    "invalidate_cache",
    "service_toggle",
]
