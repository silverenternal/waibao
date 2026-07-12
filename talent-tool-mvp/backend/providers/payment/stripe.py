"""T1405 — Stripe 支付 Provider.

签名校验: stripe.webhook.construct_event (HMAC-SHA256 over "{t}.{payload}").
其余方法在 SDK 缺失时,降级为离线最小实现 (与 MockPaymentProvider 接口一致),
便于本地开发 / CI / 单元测试.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import threading
from datetime import datetime, timezone
from typing import Any

from ..base import RetryPolicy, with_resilience
from ..exceptions import (
    AuthError,
    InvalidRequestError,
    UpstreamUnavailableError,
)
from .base import PaymentProvider
from .types import (
    CheckoutSession,
    Customer,
    Invoice,
    LineItem,
    Subscription,
    WebhookEvent,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 签名工具 (不依赖 stripe SDK)
# ---------------------------------------------------------------------------
def _sign_payload(timestamp: int, payload: bytes, secret: str) -> str:
    """Stripe v1 签名: HMAC-SHA256("{t}.{body}", secret).hex()"""
    signed = f"{timestamp}.".encode("utf-8") + payload
    return hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def verify_stripe_signature(
    payload: bytes | str,
    sig_header: str,
    *,
    secret: str,
    tolerance_seconds: int = 300,
) -> dict[str, Any]:
    """校验 Stripe webhook 签名,返回 event dict.

    - sig_header 形如: t=<ts>,v1=<hex>
    - 容忍 5 分钟时钟漂移
    - 校验失败抛 AuthError
    """
    if isinstance(payload, str):
        payload_bytes = payload.encode("utf-8")
    else:
        payload_bytes = payload
    parts: dict[str, list[str]] = {}
    for kv in (sig_header or "").split(","):
        if "=" in kv:
            k, v = kv.strip().split("=", 1)
            parts.setdefault(k, []).append(v)
    ts_str = (parts.get("t") or [None])[0]
    sigs = parts.get("v1") or []
    if not ts_str or not sigs:
        raise AuthError("stripe signature missing v1", provider="stripe")
    try:
        ts = int(ts_str)
    except ValueError as exc:
        raise AuthError(f"stripe signature ts invalid: {exc}", provider="stripe") from exc

    # 时钟漂移校验
    now = int(datetime.now(tz=timezone.utc).timestamp())
    if abs(now - ts) > tolerance_seconds:
        raise AuthError(
            "stripe signature timestamp outside tolerance",
            provider="stripe",
            details={"tolerance_seconds": tolerance_seconds},
        )

    expected = _sign_payload(ts, payload_bytes, secret)
    if not any(hmac.compare_digest(expected, s) for s in sigs):
        raise AuthError("stripe signature mismatch", provider="stripe")

    try:
        return json.loads(payload_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidRequestError(
            f"stripe payload not json: {exc}", provider="stripe"
        ) from exc


# ---------------------------------------------------------------------------
# Provider 实现
# ---------------------------------------------------------------------------
class StripeProvider(PaymentProvider):
    """Stripe 支付 Provider.

    离线模式:
        不引入 stripe SDK, 用最小自洽实现覆盖:
        - create_checkout_session
        - verify_webhook (HMAC-SHA256)
        - get_subscription
        - cancel_subscription
        - create_invoice

    在线模式:
        STRIPE_API_KEY 存在时,使用 stripe SDK 调真实 API (后续可选启用).
    """

    provider_name = "stripe"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        webhook_secret: str | None = None,
        default_currency: str = "cny",
    ) -> None:
        self.api_key = api_key
        self.webhook_secret = webhook_secret or secrets.token_hex(16)
        self._currency = default_currency.lower()
        self._lock = threading.RLock()
        # 离线 fallback 存储
        self._sessions: dict[str, CheckoutSession] = {}
        self._subscriptions: dict[str, Subscription] = {}
        self._invoices: dict[str, Invoice] = {}
        self._id_seq = 0
        self._have_sdk = False
        if api_key:
            try:  # pragma: no cover - SDK 缺失时降级
                import stripe  # type: ignore[import-not-found]

                stripe.api_key = api_key
                self._stripe = stripe
                self._have_sdk = True
            except ImportError:
                logger.warning("stripe_sdk_missing; falling back to offline mode")
                self._stripe = None

    # ----- helpers -----
    def _next_id(self, prefix: str) -> str:
        with self._lock:
            self._id_seq += 1
            return f"{prefix}_{self._id_seq:08d}"

    # ----- API -----
    @with_resilience(
        provider="payment_stripe",
        method="create_checkout_session",
        retry=RetryPolicy(max_retries=2, base_delay=0.2),
    )
    async def create_checkout_session(
        self,
        items: list[LineItem],
        customer: Customer,
        success_url: str,
        cancel_url: str,
        *,
        metadata: dict[str, str] | None = None,
    ) -> CheckoutSession:
        if not items:
            raise InvalidRequestError("items must not be empty")
        if self._have_sdk:
            return await self._sdk_create_session(
                items, customer, success_url, cancel_url, metadata=metadata
            )
        # 离线
        sid = self._next_id("cs_test")
        total = sum(it.amount_cents * it.quantity for it in items)
        currency = (items[0].currency or self._currency).lower()
        url = f"https://checkout.stripe.com/c/pay/{sid}?amount={total}&cur={currency.upper()}"
        session = CheckoutSession(
            session_id=sid,
            url=url,
            expires_at=datetime.now(tz=timezone.utc).replace(microsecond=0),
            provider=self.provider_name,
            raw={
                "items": [it.__dict__ for it in items],
                "customer": customer.__dict__,
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": metadata or {},
            },
        )
        with self._lock:
            self._sessions[sid] = session
        return session

    async def _sdk_create_session(  # pragma: no cover - 需 stripe SDK
        self,
        items: list[LineItem],
        customer: Customer,
        success_url: str,
        cancel_url: str,
        *,
        metadata: dict[str, str] | None = None,
    ) -> CheckoutSession:
        import stripe  # type: ignore

        line_items = [
            {
                "price_data": {
                    "currency": it.currency.lower(),
                    "unit_amount": it.amount_cents,
                    "product_data": {"name": it.name},
                },
                "quantity": it.quantity,
            }
            for it in items
        ]
        params: dict[str, Any] = {
            "mode": "payment",
            "line_items": line_items,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": metadata or {},
        }
        if customer.email:
            params["customer_email"] = customer.email
        if customer.customer_id:
            params["customer"] = customer.customer_id
        session = stripe.checkout.Session.create(**params)
        return CheckoutSession(
            session_id=session.id,
            url=session.url,
            expires_at=None,
            provider=self.provider_name,
            raw=session.to_dict_recursive() if hasattr(session, "to_dict_recursive") else {"id": session.id},
        )

    @with_resilience(
        provider="payment_stripe",
        method="verify_webhook",
        retry=RetryPolicy(max_retries=0),
    )
    async def verify_webhook(
        self, payload: bytes | str, signature: str
    ) -> WebhookEvent:
        event_dict = verify_stripe_signature(
            payload, signature, secret=self.webhook_secret
        )
        return WebhookEvent(
            event_id=event_dict.get("id") or self._next_id("evt"),
            event_type=event_dict.get("type", "unknown"),
            provider=self.provider_name,
            occurred_at=datetime.now(tz=timezone.utc),
            data=event_dict.get("data", {}).get("object", event_dict.get("data", {})),
            raw=event_dict,
        )

    @with_resilience(
        provider="payment_stripe",
        method="get_subscription",
        retry=RetryPolicy(max_retries=2),
    )
    async def get_subscription(self, subscription_id: str) -> Subscription:
        if self._have_sdk:  # pragma: no cover
            sub = self._stripe.Subscription.retrieve(subscription_id)
            return self._subscription_from_stripe(sub)
        with self._lock:
            sub = self._subscriptions.get(subscription_id)
        if sub is None:
            raise InvalidRequestError(
                f"subscription {subscription_id} not found",
                provider=self.provider_name,
            )
        return sub

    @with_resilience(
        provider="payment_stripe",
        method="cancel_subscription",
        retry=RetryPolicy(max_retries=2),
    )
    async def cancel_subscription(
        self,
        subscription_id: str,
        *,
        at_period_end: bool = True,
    ) -> None:
        if self._have_sdk:  # pragma: no cover
            if at_period_end:
                self._stripe.Subscription.modify(
                    subscription_id, cancel_at_period_end=True
                )
            else:
                self._stripe.Subscription.delete(subscription_id)
            return
        with self._lock:
            sub = self._subscriptions.get(subscription_id)
            if sub is None:
                raise InvalidRequestError(
                    f"subscription {subscription_id} not found",
                    provider=self.provider_name,
                )
            if at_period_end:
                sub.cancel_at_period_end = True
            else:
                sub.status = "canceled"
                sub.canceled_at = datetime.now(tz=timezone.utc)

    @with_resilience(
        provider="payment_stripe",
        method="create_invoice",
        retry=RetryPolicy(max_retries=2),
    )
    async def create_invoice(
        self,
        customer: Customer,
        items: list[LineItem],
        *,
        due_days: int = 30,
        metadata: dict[str, str] | None = None,
    ) -> Invoice:
        if not items:
            raise InvalidRequestError("items must not be empty")
        amount = sum(it.amount_cents * it.quantity for it in items)
        currency = (items[0].currency or self._currency).lower()
        inv_id = self._next_id("in")
        now = datetime.now(tz=timezone.utc)
        invoice = Invoice(
            invoice_id=inv_id,
            customer_id=customer.customer_id or self._next_id("cus"),
            amount_cents=amount,
            currency=currency,
            status="open",
            issued_at=now,
            due_at=now.replace(microsecond=0),
            hosted_url=f"https://invoice.stripe.com/i/{inv_id}",
            line_items=list(items),
            metadata=metadata or {},
        )
        with self._lock:
            self._invoices[inv_id] = invoice
        return invoice

    # ----- 内部转换 -----
    def _subscription_from_stripe(self, sub: Any) -> Subscription:  # pragma: no cover
        return Subscription(
            subscription_id=sub.id,
            customer_id=sub.customer,
            status=sub.status,
            current_period_start=None,
            current_period_end=None,
            cancel_at_period_end=bool(getattr(sub, "cancel_at_period_end", False)),
            canceled_at=None,
            plan_id=None,
            metadata=dict(getattr(sub, "metadata", {}) or {}),
            raw=sub.to_dict() if hasattr(sub, "to_dict") else {},
        )

    # ----- 测试辅助 -----
    def seed_subscription(self, subscription: Subscription) -> None:
        with self._lock:
            self._subscriptions[subscription.subscription_id] = subscription

    def make_signed_payload(
        self,
        event_type: str,
        data: dict[str, Any],
        *,
        event_id: str | None = None,
        timestamp: int | None = None,
    ) -> tuple[bytes, str]:
        """构造合法 (payload, signature_header) 用于 webhook 测试."""
        ts = timestamp or int(datetime.now(tz=timezone.utc).timestamp())
        body = {
            "id": event_id or self._next_id("evt"),
            "type": event_type,
            "data": {"object": data},
        }
        payload = json.dumps(body, sort_keys=True).encode("utf-8")
        sig = _sign_payload(ts, payload, self.webhook_secret)
        return payload, f"t={ts},v1={sig}"


__all__ = ["StripeProvider", "verify_stripe_signature"]