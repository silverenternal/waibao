"""Billing (T1405 / v10.0 T5002 split package).

The single 681-line module was split in v10.0 T5002 into three cohesive
submodules while keeping the public surface 100 % backward compatible:

    subscription — pricing (3 tiers) + checkout + subscription lifecycle
                   (create_checkout, get/cancel subscription, status mapping)
    invoice      — invoice materialisation from provider payloads +
                   the idempotent webhook handler (handle_webhook,
                   _apply_subscription_event, _invoice_from_payload)
    usage        — BillingRepo (the Supabase persistence layer for
                   subscriptions / invoices / payment_methods / webhook_events)
                   + the format_cny display helper

All logic lives in :mod:`._core`; the submodules re-export the relevant slice
so ``from services.billing.billing import BillingService`` and
``from services.billing import BillingService`` keep working unchanged.
"""
from __future__ import annotations

from ._core import (  # noqa: F401
    BillingInterval,
    BillingRepo,
    BillingService,
    CheckoutResult,
    Plan,
    PlanTier,
    SubscriptionStatus,
    format_cny,
    get_plan,
    list_plans,
)
from .invoice import *  # noqa: F401,F403
from .subscription import *  # noqa: F401,F403
from .usage import *  # noqa: F401,F403

__all__: list[str] = [
    "BillingService",
    "BillingRepo",
    "BillingInterval",
    "CheckoutResult",
    "Plan",
    "PlanTier",
    "SubscriptionStatus",
    "format_cny",
    "get_plan",
    "list_plans",
]
