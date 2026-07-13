"""Billing for paid marketplace plugins.

Lightweight ledger that records the purchase and the revenue split
between the author and the platform. Production deployments are
expected to:

* call ``StripeService`` (or WeChat Pay / Alipay adapters) from
  ``services.payments`` to actually move money;
* forward a webhook to ``mark_paid(purchase_id, payment_ref)`` to
  mark the purchase as settled;
* use ``/api/marketplace/webhook`` (see ``api/marketplace.py``) to
  receive the asynchronous payment confirmation.

The schema (in supabase/migrations/051_marketplace.sql) snapshots
``revenue_share`` at purchase time so a future change to the platform
fee never retroactively changes old purchases.
"""
from __future__ import annotations

import logging
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .catalog import CatalogService, PluginNotFoundError, PublishValidationError

logger = logging.getLogger(__name__)


class BillingError(Exception):
    pass


class PurchaseNotFoundError(BillingError):
    pass


class PurchaseStateError(BillingError):
    pass


VALID_METHODS = {"stripe", "wechat", "alipay", "manual"}
VALID_CURRENCIES = {"USD", "CNY", "EUR", "JPY"}


@dataclass
class Purchase:
    id: str
    plugin_id: str
    release_id: str | None
    tenant_id: str
    user_id: str
    amount_cents: int
    currency: str
    payment_method: str
    payment_status: str = "pending"
    payment_ref: str | None = None
    author_share_cents: int = 0
    platform_share_cents: int = 0
    created_at: float = field(default_factory=time.time)
    paid_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "plugin_id": self.plugin_id,
            "release_id": self.release_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "amount_cents": self.amount_cents,
            "currency": self.currency,
            "payment_method": self.payment_method,
            "payment_status": self.payment_status,
            "payment_ref": self.payment_ref,
            "author_share_cents": self.author_share_cents,
            "platform_share_cents": self.platform_share_cents,
            "created_at": self.created_at,
            "paid_at": self.paid_at,
        }


class BillingService:
    """Author revenue-share ledger for paid plugins."""

    def __init__(self, catalog: CatalogService) -> None:
        self.catalog = catalog
        self._purchases: dict[str, Purchase] = {}

    def create_purchase(
        self,
        *,
        plugin_id: str,
        tenant_id: str,
        user_id: str,
        payment_method: str = "stripe",
        currency: str = "USD",
        release_id: str | None = None,
    ) -> Purchase:
        if payment_method not in VALID_METHODS:
            raise PublishValidationError(
                f"invalid payment_method {payment_method!r}"
            )
        if currency not in VALID_CURRENCIES:
            raise PublishValidationError(
                f"invalid currency {currency!r}; "
                f"must be one of {sorted(VALID_CURRENCIES)}"
            )
        plugin = self.catalog.get_plugin(plugin_id=plugin_id)
        if plugin.pricing_model == "free":
            raise PublishValidationError(
                f"plugin {plugin.slug!r} is free; no purchase required"
            )
        if plugin.price_cents <= 0:
            raise PublishValidationError(
                f"plugin {plugin.slug!r} has no price set"
            )
        author_share = int(plugin.price_cents * plugin.revenue_share)
        platform_share = plugin.price_cents - author_share
        purchase = Purchase(
            id=str(uuid.uuid4()),
            plugin_id=plugin.id,
            release_id=release_id,
            tenant_id=tenant_id,
            user_id=user_id,
            amount_cents=plugin.price_cents,
            currency=currency,
            payment_method=payment_method,
            author_share_cents=author_share,
            platform_share_cents=platform_share,
        )
        self._purchases[purchase.id] = purchase
        self.catalog._store.append_audit({  # noqa: SLF001
            "plugin_id": plugin.id,
            "release_id": release_id,
            "action": "purchase",
            "actor": user_id,
            "detail": {
                "purchase_id": purchase.id,
                "tenant_id": tenant_id,
                "amount_cents": purchase.amount_cents,
                "payment_method": payment_method,
                "currency": currency,
                "payment_status": "pending",
            },
            "created_at": time.time(),
        })
        return purchase

    def mark_paid(
        self,
        *,
        purchase_id: str,
        payment_ref: str,
    ) -> Purchase:
        purchase = self._purchases.get(purchase_id)
        if purchase is None:
            raise PurchaseNotFoundError(
                f"purchase {purchase_id!r} not found"
            )
        if purchase.payment_status in ("paid",):
            return purchase
        if purchase.payment_status in ("refunded", "cancelled", "failed"):
            raise PurchaseStateError(
                f"cannot mark {purchase.payment_status!r} purchase as paid"
            )
        purchase.payment_status = "paid"
        purchase.payment_ref = payment_ref
        purchase.paid_at = time.time()
        # audit
        self.catalog._store.append_audit({  # noqa: SLF001
            "plugin_id": purchase.plugin_id,
            "action": "purchase",
            "actor": "webhook",
            "detail": {
                "purchase_id": purchase.id,
                "payment_ref": payment_ref,
                "payment_status": "paid",
            },
            "created_at": time.time(),
        })
        return purchase

    def refund(self, *, purchase_id: str, reason: str = "") -> Purchase:
        purchase = self._purchases.get(purchase_id)
        if purchase is None:
            raise PurchaseNotFoundError(
                f"purchase {purchase_id!r} not found"
            )
        if purchase.payment_status != "paid":
            raise PurchaseStateError(
                f"can only refund paid purchases (current: "
                f"{purchase.payment_status!r})"
            )
        purchase.payment_status = "refunded"
        self.catalog._store.append_audit({  # noqa: SLF001
            "plugin_id": purchase.plugin_id,
            "action": "purchase",
            "actor": "refund",
            "detail": {
                "purchase_id": purchase.id,
                "reason": reason,
                "payment_status": "refunded",
            },
            "created_at": time.time(),
        })
        return purchase

    def get_purchase(self, purchase_id: str) -> Purchase:
        p = self._purchases.get(purchase_id)
        if p is None:
            raise PurchaseNotFoundError(
                f"purchase {purchase_id!r} not found"
            )
        return p

    def list_purchases(
        self,
        *,
        tenant_id: str | None = None,
        plugin_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Purchase]:
        items = list(self._purchases.values())
        if tenant_id is not None:
            items = [p for p in items if p.tenant_id == tenant_id]
        if plugin_id is not None:
            items = [p for p in items if p.plugin_id == plugin_id]
        if status is not None:
            items = [p for p in items if p.payment_status == status]
        items.sort(key=lambda p: -p.created_at)
        return items[:limit]

    def author_earnings(self, *, author_id: str) -> dict[str, Any]:
        """Aggregate pending + paid earnings for an author."""
        # Build a set of plugin ids for this author.
        plugin_ids = {
            p.id for p in self.catalog._store.plugins.values()  # noqa: SLF001
            if p.author_id == author_id
        }
        paid = [
            p for p in self._purchases.values()
            if p.plugin_id in plugin_ids and p.payment_status == "paid"
        ]
        pending = [
            p for p in self._purchases.values()
            if p.plugin_id in plugin_ids and p.payment_status == "pending"
        ]
        total_paid = sum(p.author_share_cents for p in paid)
        total_pending = sum(p.author_share_cents for p in pending)
        return {
            "author_id": author_id,
            "paid_count": len(paid),
            "pending_count": len(pending),
            "paid_cents": total_paid,
            "pending_cents": total_pending,
            "currency_breakdown": self._group_by_currency(paid),
        }

    def _group_by_currency(
        self,
        purchases: list[Purchase],
    ) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for p in purchases:
            slot = out.setdefault(p.currency, {"count": 0, "cents": 0})
            slot["count"] += 1
            slot["cents"] += p.author_share_cents
        return out

    # ---- webhook signature ---------------------------------------------

    def verify_webhook(
        self,
        *,
        payload: bytes,
        signature: str,
        secret: str,
        tolerance_seconds: int = 300,
    ) -> dict[str, Any]:
        """Verify a Strapi / Stripe / WeChat-style webhook.

        Payload format: ``<unix_ts>.<body>``. Signature is hex(HMAC-SHA256).
        """
        import hashlib
        import hmac
        import json
        try:
            ts_str, body = payload.split(b".", 1)
            ts = int(ts_str)
        except Exception as exc:
            raise BillingError(f"malformed webhook payload: {exc}")
        if abs(time.time() - ts) > tolerance_seconds:
            raise BillingError("webhook timestamp outside tolerance")
        expected = hmac.new(
            secret.encode("utf-8"),
            body, hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature or ""):
            raise BillingError("invalid webhook signature")
        try:
            return json.loads(body)
        except Exception as exc:
            raise BillingError(f"invalid webhook body json: {exc}")


def generate_idempotency_key() -> str:
    """Generate a 32-char URL-safe idempotency key for purchase creation."""
    return secrets.token_urlsafe(24)
