"""Billing — Subscription slice (v10.0 T5002 split).

Covers pricing (the 3 tiers + ``Plan`` dataclass), checkout creation and the
subscription read/cancel lifecycle.  Logic lives in :mod:`._core`.
"""
from __future__ import annotations

from ._core import (  # noqa: F401
    BillingInterval,
    BillingService,
    CheckoutResult,
    Plan,
    PlanTier,
    SubscriptionStatus,
    get_plan,
    list_plans,
)

__all__ = [
    "Plan",
    "PlanTier",
    "BillingInterval",
    "SubscriptionStatus",
    "CheckoutResult",
    "BillingService",
    "list_plans",
    "get_plan",
]
