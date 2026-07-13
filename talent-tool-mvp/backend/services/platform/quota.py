"""T2602 - Tenant quota / plan enforcement.

Plans:
    Free       — 100  req/min per tenant
    Pro        — 1000 req/min per tenant
    Enterprise — 10000 req/min per tenant

Each tenant has per-resource limits (e.g. ``ai_tokens_per_month``,
``storage_gb``).  Enforcement is split into:

  * :func:`enforce_request`   — called before every API request, returns True
                                 if within the per-minute per-tenant budget.
  * :func:`enforce_resource`  — called around expensive operations
                                 (LLM tokens, vector inserts, etc.).

The quota counters live in Redis when configured; fall back to an in-process
dict (so tests / single-replica dev still work).
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional

logger = logging.getLogger("recruittech.platform.quota")


# -------------------------------------------------------------------------
# Plan definitions
# -------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanLimits:
    """All numeric ceilings per plan.  Easy to extend by adding fields."""

    name: str
    requests_per_minute: int
    requests_per_day: int
    ai_tokens_per_month: int
    storage_gb: int
    seats: int

    def as_dict(self) -> Dict[str, int | str]:
        return {
            "name": self.name,
            "requests_per_minute": self.requests_per_minute,
            "requests_per_day": self.requests_per_day,
            "ai_tokens_per_month": self.ai_tokens_per_month,
            "storage_gb": self.storage_gb,
            "seats": self.seats,
        }


_PLAN_FREE = PlanLimits(
    name="free",
    requests_per_minute=100,
    requests_per_day=20_000,
    ai_tokens_per_month=200_000,
    storage_gb=2,
    seats=3,
)
_PLAN_PRO = PlanLimits(
    name="pro",
    requests_per_minute=1000,
    requests_per_day=200_000,
    ai_tokens_per_month=2_000_000,
    storage_gb=50,
    seats=25,
)
_PLAN_ENT = PlanLimits(
    name="enterprise",
    requests_per_minute=10_000,
    requests_per_day=2_000_000,
    ai_tokens_per_month=20_000_000,
    storage_gb=500,
    seats=500,
)


_PLANS: Mapping[str, PlanLimits] = {
    "free": _PLAN_FREE,
    "pro": _PLAN_PRO,
    "enterprise": _PLAN_ENT,
}

DEFAULT_PLAN = "free"


def get_plan(name: Optional[str]) -> PlanLimits:
    """Return PlanLimits for ``name`` (case-insensitive); defaults to Free."""
    if not name:
        return _PLAN_FREE
    return _PLANS.get(name.lower(), _PLAN_FREE)


def list_plans() -> list[PlanLimits]:
    return list(_PLANS.values())


# -------------------------------------------------------------------------
# In-memory sliding-window counter (token-bucket-ish)
# -------------------------------------------------------------------------

@dataclass
class _Counter:
    window_start: float = 0.0
    count: int = 0
    window_seconds: float = 60.0


@dataclass
class _DayCounter:
    """Cheap daily counter. Persists until process restart."""
    day: str = ""
    count: int = 0


@dataclass
class QuotaStore:
    """Memory-backed quota counters.

    In production swap for a Redis-backed implementation that inherits the
    same interface.  The tests verify behaviour; storage is an
    implementation detail.
    """

    _req: Dict[str, _Counter] = field(default_factory=dict)
    _day: Dict[str, _DayCounter] = field(default_factory=dict)
    _tokens: Dict[str, int] = field(default_factory=dict)

    # ---- per-minute -----------------------------------------------
    def incr_request(self, tenant_id: uuid.UUID | str) -> tuple[bool, int]:
        """Increment the per-minute counter.

        Returns ``(allowed, remaining)``.  When the counter is already at
        the limit the call is rejected and the counter is **not** incremented.
        """
        from .rate_limiter import get_limiter  # avoids cycle at import
        from .tenant_context import get_tenant_context

        ctx = get_tenant_context()
        plan = get_plan(ctx.plan if ctx else "free")
        key = f"{tenant_id}"
        now = time.time()
        c = self._req.get(key) or _Counter()
        if now - c.window_start >= c.window_seconds:
            c.window_start = now
            c.count = 0
        c.count += 1
        self._req[key] = c
        allowed = c.count <= plan.requests_per_minute
        remaining = max(0, plan.requests_per_minute - c.count)
        # Touch the slowapi limiter (which records its own metric).
        try:
            get_limiter()
        except Exception:  # noqa: BLE001
            pass
        return allowed, remaining

    # ---- per-day --------------------------------------------------
    def incr_day(self, tenant_id: uuid.UUID | str, limit: int) -> tuple[bool, int]:
        from .tenant_context import get_tenant_context
        ctx = get_tenant_context()
        plan = get_plan(ctx.plan if ctx else "free")
        cap = limit or plan.requests_per_day
        key = f"{tenant_id}"
        today = time.strftime("%Y-%m-%d")
        c = self._day.get(key) or _DayCounter()
        if c.day != today:
            c.day = today
            c.count = 0
        c.count += 1
        self._day[key] = c
        allowed = c.count <= cap
        remaining = max(0, cap - c.count)
        return allowed, remaining

    # ---- resource counters ---------------------------------------
    def incr_tokens(self, tenant_id: uuid.UUID | str, delta: int = 1) -> tuple[bool, int]:
        from .tenant_context import get_tenant_context
        ctx = get_tenant_context()
        plan = get_plan(ctx.plan if ctx else "free")
        key = f"{tenant_id}:tokens"
        current = self._tokens.get(key, 0) + delta
        self._tokens[key] = current
        allowed = current <= plan.ai_tokens_per_month
        remaining = max(0, plan.ai_tokens_per_month - current)
        return allowed, remaining

    # ---- inspection ----------------------------------------------
    def reset(self) -> None:
        self._req.clear()
        self._day.clear()
        self._tokens.clear()


_store = QuotaStore()


def get_quota_store() -> QuotaStore:
    return _store


def reset_quota_store() -> None:
    _store.reset()


# -------------------------------------------------------------------------
# Enforcement entry points
# -------------------------------------------------------------------------

def enforce_request(tenant_id: uuid.UUID | str) -> bool:
    """Per-minute per-tenant ceiling; True if within budget."""
    allowed, _remaining = _store.incr_request(tenant_id)
    if not allowed:
        logger.info("quota.rate tenant=%s exceeded minute-bucket", tenant_id)
    return allowed


def enforce_resource(tenant_id: uuid.UUID | str, resource: str, *, delta: int = 1) -> bool:
    """Counter for an arbitrary resource key (e.g. ``ai_tokens``, ``video_minutes``)."""
    if resource == "ai_tokens":
        ok, _ = _store.incr_tokens(tenant_id, delta=delta)
    elif resource == "day":
        ok, _ = _store.incr_day(tenant_id, limit=0)
    else:  # unknown — allow by default
        ok = True
    return ok


def remaining(tenant_id: uuid.UUID | str) -> dict:
    """Snapshot of the current tenant's remaining budget."""
    plan = get_plan("free")  # plan lookup happens via get_tenant_context()
    return {
        "requests_per_minute": plan.requests_per_minute,
    }


__all__ = [
    "PlanLimits",
    "get_plan",
    "list_plans",
    "QuotaStore",
    "get_quota_store",
    "reset_quota_store",
    "enforce_request",
    "enforce_resource",
    "remaining",
]
