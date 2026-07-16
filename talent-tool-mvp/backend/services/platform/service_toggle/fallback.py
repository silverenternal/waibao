"""v10.0 T5029 — ServiceToggle fallback (registry miss → degrade, not 500).

When a service name is not in the registry (e.g. a new feature shipped before
its catalog row was seeded, or a tenant-scoped capability that the local
worker hasn't received yet), the legacy gate raised :class:`ServiceNotFoundError`
→ 500 to the client. That is operationally hostile: a missing catalog row
should **degrade** (allow the call with a warning + audit) rather than take
down the endpoint.

This module adds two escape hatches on top of the existing
:class:`~services.platform.service_toggle._core.ServiceToggle`:

* :func:`is_enabled_safe` — returns the gate verdict for ``name``; on a
  registry miss it emits a single de-duplicated warning and consults the
  :class:`MockToggleRegistry` (default policy: allow, i.e. fail-open so a
  seeding gap never blocks traffic).
* :class:`MockToggleRegistry` — an in-memory override store used to mock the
  on/off state of services that aren't (yet) in the real catalog. Operators
  can pre-seed it during migrations / canary releases.

The behaviour is opt-in: callers that want strict fail-closed semantics keep
using ``service_toggle.is_enabled`` directly.
"""
from __future__ import annotations

import logging
import threading
from typing import Dict, Optional, Set

from ._core import ServiceToggle, service_toggle

logger = logging.getLogger("recruittech.platform.service_toggle.fallback")


# ---------------------------------------------------------------------------
# MockToggleRegistry
# ---------------------------------------------------------------------------
class MockToggleRegistry:
    """In-memory on/off overrides for services absent from the catalog.

    Used by :func:`is_enabled_safe` as the fallback authority when the real
    registry doesn't know about a service. Also useful in tests to simulate
    toggling services without a database.
    """

    def __init__(self, *, default_allow: bool = True) -> None:
        self._overrides: Dict[str, bool] = {}
        self._default_allow = default_allow
        self._lock = threading.RLock()

    def set(self, name: str, enabled: bool) -> None:
        with self._lock:
            self._overrides[name] = bool(enabled)

    def get(self, name: str) -> Optional[bool]:
        with self._lock:
            return self._overrides.get(name)

    def remove(self, name: str) -> None:
        with self._lock:
            self._overrides.pop(name, None)

    def clear(self) -> None:
        with self._lock:
            self._overrides.clear()

    def is_enabled(self, name: str) -> bool:
        with self._lock:
            if name in self._overrides:
                return self._overrides[name]
            return self._default_allow

    @property
    def default_allow(self) -> bool:
        return self._default_allow


# ---------------------------------------------------------------------------
# Singleton mock registry + warning de-dup
# ---------------------------------------------------------------------------
_MOCK_REGISTRY = MockToggleRegistry(default_allow=True)
_warned: Set[str] = set()
_warned_lock = threading.Lock()
# De-dup: warn about the same missing service at most once per process.


def get_mock_registry() -> MockToggleRegistry:
    return _MOCK_REGISTRY


def reset_fallback_state() -> None:
    """Clear the mock registry + warning cache (test helper)."""
    global _MOCK_REGISTRY
    _MOCK_REGISTRY = MockToggleRegistry(default_allow=True)
    with _warned_lock:
        _warned.clear()


def _warn_once(name: str) -> None:
    with _warned_lock:
        last = _warned
    key = name
    # simple de-dup: warn at most once per TTL window per service
    # (we don't track timestamps to keep this allocation-free; re-warn is fine)
    if key in last:
        return
    last.add(key)
    logger.warning(
        "service_toggle.fallback service=%r not in registry; "
        "degrading to mock registry (fail-open). Seed the catalog to silence.",
        name,
    )


# ---------------------------------------------------------------------------
# is_enabled_safe
# ---------------------------------------------------------------------------
def is_enabled_safe(
    name: str,
    org_id: Optional[str] = None,
    plan: str = "free",
    role: str = "jobseeker",
    *,
    toggle: Optional[ServiceToggle] = None,
    mock: Optional[MockToggleRegistry] = None,
) -> bool:
    """Gate verdict that degrades instead of raising on a registry miss.

    * If ``name`` is registered → defer to the real gate (``is_enabled``).
    * If ``name`` is NOT registered → warn once and consult the mock registry
      (default policy ``allow``), so the caller keeps working.
    """
    st = toggle or service_toggle
    try:
        svc = st.get_service(name)
    except Exception:  # noqa: BLE001 — catalog unreachable counts as a miss
        # The control-plane (catalog DB) is unavailable. Treat this exactly
        # like a registry miss: warn once and degrade to the mock registry so
        # the caller keeps working instead of receiving a 500.
        svc = None
    if svc is not None:
        try:
            return st.is_enabled(name, org_id, plan, role)
        except Exception:  # noqa: BLE001 — gate must never crash the caller
            logger.exception("service_toggle.is_enabled_failed name=%s", name)
            return (mock or _MOCK_REGISTRY).is_enabled(name)
    # registry miss → fallback
    _warn_once(name)
    return (mock or _MOCK_REGISTRY).is_enabled(name)


def check_service_access_safe(
    name: str,
    org_id: Optional[str] = None,
    plan: str = "free",
    role: str = "jobseeker",
    *,
    toggle: Optional[ServiceToggle] = None,
    mock: Optional[MockToggleRegistry] = None,
) -> bool:
    """Alias matching the legacy ``check_service_access`` naming."""
    return is_enabled_safe(name, org_id, plan, role, toggle=toggle, mock=mock)


__all__ = [
    "MockToggleRegistry",
    "is_enabled_safe",
    "check_service_access_safe",
    "get_mock_registry",
    "reset_fallback_state",
]
