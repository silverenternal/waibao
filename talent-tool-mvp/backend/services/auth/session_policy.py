"""v10.0 T5018 — Session lifecycle policy: idle / absolute / impossible-travel.

The existing :mod:`services.auth.session` mints access + refresh tokens but
does not enforce the three enterprise session controls SOC2 + ISO 27001
auditors look for:

* **Idle timeout** — a session that has been *inactive* for more than N
  minutes must be revoked, even if its tokens are still technically valid
  (e.g. a laptop left unlocked in a café).  Default **30 minutes**.
* **Absolute timeout** — a session must die N hours after it was *created*,
  no matter how active it is, forcing a fresh authentication.  Default
  **8 hours**.
* **Impossible-travel (geo) detection** — two consecutive accesses whose
  geographic distance implies a travel speed faster than any commercial
  flight (> ~900 km/h, configurable) are flagged as "impossible travel" and
  (optionally) force re-authentication.  This catches stolen-token reuse
  from a different continent.

This module is a **pure policy engine**: it takes session metadata (timestamps
+ optional geo points) and returns a :class:`SessionVerdict`.  The session
manager / middleware is responsible for recording ``last_seen_at`` and
``last_geo`` on each authenticated request and calling :func:`evaluate`.

Design notes
------------
* Distances use the haversine formula (no external deps).
* The impossible-travel check is *advisory* by default (returns ``geo_alert``
  in the verdict) so operators can tune the threshold before flipping it to
  enforcing; set ``SSO_IMPOSSIBLE_TRAVEL_ENFORCE=1`` to make it revoke.
* All thresholds are env-overridable for per-deployment tuning.
"""
from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("waibao.auth.session_policy")

# ---------------------------------------------------------------------------
# Configuration (all env-overridable)
# ---------------------------------------------------------------------------
IDLE_TIMEOUT_SECONDS = int(os.getenv("SSO_IDLE_TIMEOUT_SECONDS", str(30 * 60)))      # 30 min
ABSOLUTE_TIMEOUT_SECONDS = int(os.getenv("SSO_ABSOLUTE_TIMEOUT_SECONDS", str(8 * 3600)))  # 8 h
# Max plausible ground speed (km/h). Commercial flights cruise ~900 km/h.
IMPOSSIBLE_TRAVEL_KMH = float(os.getenv("SSO_IMPOSSIBLE_TRAVEL_KMH", "900"))
IMPOSSIBLE_TRAVEL_ENFORCE = os.getenv("SSO_IMPOSSIBLE_TRAVEL_ENFORCE", "0").lower() in (
    "1", "true", "yes"
)


@dataclass(frozen=True)
class GeoPoint:
    """A (lat, lon) pair in decimal degrees."""
    lat: float
    lon: float


@dataclass
class SessionMeta:
    """The per-session facts the policy needs.  Mirrors the fields the
    session manager already tracks; callers populate from there."""
    session_id: str
    created_at: float           # epoch seconds
    last_seen_at: float         # epoch seconds of the last activity
    last_geo: Optional[GeoPoint] = None
    now: float = 0.0            # optional override of "now" (tests)


@dataclass
class SessionVerdict:
    """Outcome of :func:`evaluate`."""
    valid: bool
    reason: Optional[str] = None           # idle_expired | absolute_expired | impossible_travel
    idle_seconds: float = 0.0
    age_seconds: float = 0.0
    geo_alert: bool = False
    geo_speed_kmh: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "reason": self.reason,
            "idle_seconds": round(self.idle_seconds, 1),
            "age_seconds": round(self.age_seconds, 1),
            "geo_alert": self.geo_alert,
            "geo_speed_kmh": self.geo_speed_kmh,
        }


# ---------------------------------------------------------------------------
# Haversine distance
# ---------------------------------------------------------------------------
_EARTH_RADIUS_KM = 6371.0088


def haversine_km(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance between two points in kilometres."""
    lat1 = math.radians(a.lat)
    lat2 = math.radians(b.lat)
    dlat = math.radians(b.lat - a.lat)
    dlon = math.radians(b.lon - a.lon)
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, h)))


# ---------------------------------------------------------------------------
# Policy engine
# ---------------------------------------------------------------------------
def evaluate(
    meta: SessionMeta,
    *,
    new_geo: Optional[GeoPoint] = None,
    idle_timeout: int = IDLE_TIMEOUT_SECONDS,
    absolute_timeout: int = ABSOLUTE_TIMEOUT_SECONDS,
    impossible_travel_kmh: float = IMPOSSIBLE_TRAVEL_KMH,
    enforce_geo: bool = IMPOSSIBLE_TRAVEL_ENFORCE,
) -> SessionVerdict:
    """Return a :class:`SessionVerdict` for ``meta`` given optional ``new_geo``.

    The caller should:
      1. record ``meta.last_seen_at`` + ``meta.last_geo`` from the session row,
      2. pass the *request's* geo as ``new_geo`` (or ``None`` if unknown),
      3. if ``verdict.valid`` is False, revoke the session / force re-auth.
    """
    import time
    now = meta.now or time.time()
    age = max(0.0, now - meta.created_at)
    idle = max(0.0, now - meta.last_seen_at) if meta.last_seen_at else age

    # 1. absolute timeout — hard kill
    if age > absolute_timeout:
        return SessionVerdict(
            valid=False, reason="absolute_expired",
            idle_seconds=idle, age_seconds=age,
        )
    # 2. idle timeout — hard kill
    if idle > idle_timeout:
        return SessionVerdict(
            valid=False, reason="idle_expired",
            idle_seconds=idle, age_seconds=age,
        )

    # 3. impossible travel — advisory or hard kill
    geo_alert = False
    speed: Optional[float] = None
    if new_geo is not None and meta.last_geo is not None:
        elapsed_h = max(1e-6, (now - meta.last_seen_at) / 3600.0)
        dist = haversine_km(meta.last_geo, new_geo)
        speed = dist / elapsed_h
        if speed > impossible_travel_kmh:
            geo_alert = True
            if enforce_geo:
                logger.warning(
                    "session.impossible_travel session=%s speed=%.0f km/h",
                    meta.session_id, speed,
                )
                return SessionVerdict(
                    valid=False, reason="impossible_travel",
                    idle_seconds=idle, age_seconds=age,
                    geo_alert=True, geo_speed_kmh=speed,
                )
    return SessionVerdict(
        valid=True, idle_seconds=idle, age_seconds=age,
        geo_alert=geo_alert, geo_speed_kmh=speed,
    )


def should_refresh_token(meta: SessionMeta, *, access_ttl: float) -> bool:
    """True when the session's access token is within the last 20 % of its
    TTL — a hint for the middleware to proactively rotate."""
    import time
    now = meta.now or time.time()
    remaining = (meta.created_at + access_ttl) - now
    return remaining < (access_ttl * 0.2)


__all__ = [
    "IDLE_TIMEOUT_SECONDS",
    "ABSOLUTE_TIMEOUT_SECONDS",
    "IMPOSSIBLE_TRAVEL_KMH",
    "IMPOSSIBLE_TRAVEL_ENFORCE",
    "GeoPoint",
    "SessionMeta",
    "SessionVerdict",
    "haversine_km",
    "evaluate",
    "should_refresh_token",
]
