"""v10.0 T5026 — Real-time LLM cost / token tracker with per-tenant budgets.

A focused, in-process cost engine that:

* Records every LLM call's **token usage** (prompt + completion + reasoning)
  AND its **USD cost** in one shot, keyed by (tenant, provider, model, day).
* Computes the USD cost from a pluggable price table when only tokens are
  known, so callers that don't natively report cost are still metered.
* Enforces **per-tenant daily budgets** with three soft tiers
  (warn / throttle / block) and fires an alert callback at each threshold
  crossing — wired to the existing alerting channels by the host.
* Exposes a snapshot API for the cost dashboard
  (:meth:`RealtimeCostTracker.snapshot`) that returns today's spend, token
  counts, and per-provider breakdown.

It interoperates with the older aggregators:

* :class:`providers.base.CostTracker` (the in-call fast path) emits a cost
  event that can be forwarded here via :meth:`ingest_event`.
* :class:`services.observability.cost_tracker.CostTrackerService` remains the
  Supabase persistence layer; this module is the real-time, budget-aware
  front-end that feeds it.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("waibao.platform.cost_tracker")


# ---------------------------------------------------------------------------
# Budget tiers
# ---------------------------------------------------------------------------
class BudgetTier(str, Enum):
    OK = "ok"
    WARN = "warn"        # >= warn_pct of budget
    THROTTLE = "throttle"  # >= throttle_pct
    BLOCK = "block"      # >= 100 %


@dataclass
class BudgetConfig:
    daily_budget_usd: float = 50.0
    warn_pct: float = 0.80
    throttle_pct: float = 0.95

    def tier_for(self, spent: float) -> BudgetTier:
        ratio = spent / self.daily_budget_usd if self.daily_budget_usd > 0 else 0.0
        if ratio >= 1.0:
            return BudgetTier.BLOCK
        if ratio >= self.throttle_pct:
            return BudgetTier.THROTTLE
        if ratio >= self.warn_pct:
            return BudgetTier.WARN
        return BudgetTier.OK


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens + self.reasoning_tokens

    def add(self, other: "TokenUsage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.reasoning_tokens += other.reasoning_tokens


@dataclass
class AlertEvent:
    tenant: str
    tier: BudgetTier
    spent: float
    budget: float
    ratio: float
    at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant": self.tenant, "tier": self.tier.value,
            "spent": round(self.spent, 6), "budget": self.budget,
            "ratio": round(self.ratio, 4), "at": self.at,
        }


# ---------------------------------------------------------------------------
# Price table (USD per 1M tokens): (input, output)
# ---------------------------------------------------------------------------
DEFAULT_PRICING: Dict[str, Tuple[float, float]] = {
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4-turbo": (10.0, 30.0),
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-opus": (15.0, 75.0),
    "claude-3-haiku": (0.25, 1.25),
    "deepseek-chat": (0.14, 0.28),
    "glm-4": (0.5, 0.5),
    "qwen-plus": (0.4, 1.2),
    "mock-model": (0.0, 0.0),
    "unknown": (0.0, 0.0),
}


def estimate_cost(usage: TokenUsage, model: str,
                  pricing: Optional[Dict[str, Tuple[float, float]]] = None) -> float:
    """Estimate USD cost from token usage + a price table (per 1M tokens)."""
    table = pricing or DEFAULT_PRICING
    key = model
    if key not in table:
        # case-insensitive / prefix fallback
        lower = {k.lower(): v for k, v in table.items()}
        key = next((k for k in lower if model.lower().startswith(k)), "unknown")
        in_p, out_p = lower.get(key, (0.0, 0.0))
    else:
        in_p, out_p = table[key]
    return (usage.prompt_tokens * in_p + usage.completion_tokens * out_p) / 1_000_000.0


# ---------------------------------------------------------------------------
# RealtimeCostTracker
# ---------------------------------------------------------------------------
class BudgetExceededError(Exception):
    """Raised when a tenant has hit its BLOCK budget tier."""

    def __init__(self, tenant: str, spent: float, budget: float) -> None:
        super().__init__(
            f"tenant={tenant} budget blocked: spent {spent:.4f} >= {budget:.2f} USD"
        )
        self.tenant = tenant
        self.spent = spent
        self.budget = budget


class RealtimeCostTracker:
    """In-process real-time cost/token meter with per-tenant budgets."""

    def __init__(
        self,
        *,
        budgets: Optional[Dict[str, BudgetConfig]] = None,
        default_budget: Optional[BudgetConfig] = None,
        pricing: Optional[Dict[str, Tuple[float, float]]] = None,
        alert_callback: Optional[Callable[[AlertEvent], None]] = None,
    ) -> None:
        self._budgets = dict(budgets or {})
        self._default = default_budget or self._load_default_budget()
        self._pricing = pricing or dict(DEFAULT_PRICING)
        self._alert_cb = alert_callback
        self._lock = threading.RLock()
        # tenant -> usage aggregates
        self._spend: Dict[str, float] = defaultdict(float)
        self._tokens: Dict[str, TokenUsage] = defaultdict(TokenUsage)
        # tenant -> provider:model -> spend (for the breakdown)
        self._breakdown: Dict[str, Dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        # tenant -> last tier (so we only alert on transitions)
        self._tier: Dict[str, BudgetTier] = defaultdict(lambda: BudgetTier.OK)
        # buffer forwarded to the persistence layer (observability)
        self._persist_buffer: List[Dict[str, Any]] = []
        self._persist_cb: Optional[Callable[[List[Dict[str, Any]]], None]] = None

    # ---- config ---------------------------------------------------------
    @staticmethod
    def _load_default_budget() -> BudgetConfig:
        budget = float(os.getenv("DAILY_BUDGET_USD", "50.0"))
        return BudgetConfig(daily_budget_usd=budget)

    def set_budget(self, tenant: str, config: BudgetConfig) -> None:
        with self._lock:
            self._budgets[tenant] = config
            self._tier[tenant] = BudgetTier.OK  # reset tiering on reconfig

    def set_persistence(self, cb: Optional[Callable[[List[Dict[str, Any]]], None]]) -> None:
        self._persist_cb = cb

    def _budget_for(self, tenant: str) -> BudgetConfig:
        return self._budgets.get(tenant, self._default)

    # ---- recording ------------------------------------------------------
    def record(
        self,
        tenant: str,
        *,
        provider: str = "unknown",
        model: str = "unknown",
        cost_usd: Optional[float] = None,
        usage: Optional[TokenUsage] = None,
    ) -> AlertEvent:
        """Record one LLM call. Returns the (possibly updated) AlertEvent.

        When ``cost_usd`` is None we estimate it from ``usage`` + the price
        table. When both are missing the call is a no-op.
        """
        if cost_usd is None and usage is None:
            return AlertEvent(tenant, BudgetTier.OK, 0.0, self._budget_for(tenant).daily_budget_usd, 0.0)
        u = usage or TokenUsage()
        if cost_usd is None:
            cost_usd = estimate_cost(u, model, self._pricing)
        if cost_usd <= 0 and u.total == 0:
            return AlertEvent(tenant, BudgetTier.OK, 0.0, self._budget_for(tenant).daily_budget_usd, 0.0)

        with self._lock:
            self._spend[tenant] += cost_usd
            self._tokens[tenant].add(u)
            self._breakdown[tenant][f"{provider}:{model}"] += cost_usd
            budget = self._budget_for(tenant)
            spent = self._spend[tenant]
            new_tier = budget.tier_for(spent)
            old_tier = self._tier[tenant]
            ratio = spent / budget.daily_budget_usd if budget.daily_budget_usd > 0 else 0.0
            alert = AlertEvent(tenant=tenant, tier=new_tier, spent=spent,
                               budget=budget.daily_budget_usd, ratio=ratio)
            # buffer for persistence
            self._persist_buffer.append({
                "tenant_id": tenant, "provider": provider, "model": model,
                "cost_usd": float(cost_usd),
                "prompt_tokens": u.prompt_tokens,
                "completion_tokens": u.completion_tokens,
                "reasoning_tokens": u.reasoning_tokens,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            })
            tier_changed = new_tier != old_tier
            if tier_changed:
                self._tier[tenant] = new_tier
            buffered = list(self._persist_buffer)
            self._persist_buffer.clear()
        # persist outside the lock (non-blocking)
        if self._persist_cb is not None:
            try:
                self._persist_cb(buffered)
            except Exception:  # noqa: BLE001
                logger.exception("cost_tracker.persist_failed")
        # alert on transitions OR every call at BLOCK
        if tier_changed or new_tier == BudgetTier.BLOCK:
            self._fire_alert(alert)
        return alert

    def ingest_event(self, event: Dict[str, Any]) -> AlertEvent:
        """Forward a providers.base.CostTracker-style event."""
        usage = TokenUsage(
            prompt_tokens=int(event.get("prompt_tokens", 0) or 0),
            completion_tokens=int(event.get("completion_tokens", 0) or 0),
            reasoning_tokens=int(event.get("reasoning_tokens", 0) or 0),
        )
        return self.record(
            tenant=str(event.get("tenant") or event.get("tenant_id") or "default"),
            provider=str(event.get("provider") or "unknown"),
            model=str(event.get("model") or "unknown"),
            cost_usd=float(event.get("cost_usd")) if event.get("cost_usd") is not None else None,
            usage=usage,
        )

    # ---- enforcement ----------------------------------------------------
    def check(self, tenant: str) -> BudgetTier:
        """Return the current tier for a tenant (no recording)."""
        with self._lock:
            return self._budget_for(tenant).tier_for(self._spend[tenant])

    def enforce(self, tenant: str) -> None:
        """Raise :class:`BudgetExceededError` if the tenant is at BLOCK tier."""
        tier = self.check(tenant)
        if tier == BudgetTier.BLOCK:
            budget = self._budget_for(tenant)
            raise BudgetExceededError(tenant, self._spend[tenant],
                                      budget.daily_budget_usd)

    # ---- read path ------------------------------------------------------
    def spent(self, tenant: str) -> float:
        with self._lock:
            return self._spend.get(tenant, 0.0)

    def tokens(self, tenant: str) -> TokenUsage:
        with self._lock:
            t = self._tokens.get(tenant)
            return TokenUsage(t.prompt_tokens, t.completion_tokens, t.reasoning_tokens) if t else TokenUsage()

    def snapshot(self, tenant: Optional[str] = None) -> Dict[str, Any]:
        """Return a dashboard-ready snapshot. ``tenant=None`` returns all."""
        with self._lock:
            tenants = [tenant] if tenant else sorted(self._spend)
            out: Dict[str, Any] = {}
            for t in tenants:
                budget = self._budget_for(t)
                spent = self._spend.get(t, 0.0)
                out[t] = {
                    "spent_usd": round(spent, 6),
                    "budget_usd": budget.daily_budget_usd,
                    "ratio": round(spent / budget.daily_budget_usd, 4)
                    if budget.daily_budget_usd > 0 else 0.0,
                    "tier": self._budget_for(t).tier_for(spent).value,
                    "tokens": {
                        "prompt": self._tokens[t].prompt_tokens,
                        "completion": self._tokens[t].completion_tokens,
                        "reasoning": self._tokens[t].reasoning_tokens,
                        "total": self._tokens[t].total,
                    },
                    "breakdown": dict(self._breakdown.get(t, {})),
                }
            return out

    def reset(self) -> None:
        """Clear all aggregates (test helper)."""
        with self._lock:
            self._spend.clear()
            self._tokens.clear()
            self._breakdown.clear()
            self._tier.clear()
            self._persist_buffer.clear()

    # ---- internals ------------------------------------------------------
    def _fire_alert(self, alert: AlertEvent) -> None:
        if self._alert_cb is None:
            logger.warning(
                "cost_tracker.budget_alert tenant=%s tier=%s spent=%.4f budget=%.2f",
                alert.tenant, alert.tier.value, alert.spent, alert.budget,
            )
            return
        try:
            self._alert_cb(alert)
        except Exception:  # noqa: BLE001
            logger.exception("cost_tracker.alert_callback_failed")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_TRACKER: Optional[RealtimeCostTracker] = None


def get_cost_tracker() -> RealtimeCostTracker:
    global _TRACKER
    if _TRACKER is None:
        _TRACKER = RealtimeCostTracker()
    return _TRACKER


def set_cost_tracker(tracker: RealtimeCostTracker) -> None:
    global _TRACKER
    _TRACKER = tracker


def reset_cost_tracker() -> None:
    global _TRACKER
    _TRACKER = None


__all__ = [
    "BudgetTier",
    "BudgetConfig",
    "BudgetExceededError",
    "TokenUsage",
    "AlertEvent",
    "RealtimeCostTracker",
    "DEFAULT_PRICING",
    "estimate_cost",
    "get_cost_tracker",
    "set_cost_tracker",
    "reset_cost_tracker",
]
