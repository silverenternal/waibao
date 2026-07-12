"""支付供应商 Mock 实现.

完全离线,用于本地开发 / 单元测试 / CI.
不依赖 Stripe / 微信支付 SDK.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
from datetime import datetime, timedelta, timezone

from ..base import RetryPolicy, with_resilience
from ..exceptions import AuthError, InvalidRequestError
from .base import PaymentProvider
from .types import (
    CheckoutSession,
    Customer,
    Invoice,
    LineItem,
    Subscription,
    WebhookEvent,
)


class MockPaymentProvider(PaymentProvider):
    """内存支付实现.

    - checkout session 存在 _sessions dict 里
    - 签名校验: HMAC-SHA256(secret, payload),用固定的 _webhook_secret
    - 订阅 / 发票 同样内存保存,提供 query / cancel 完整行为
    """

    provider_name = "mock_payment"

    def __init__(
        self,
        webhook_secret: str = "mock-secret",
        default_currency: str = "USD",
    ) -> None:
        self._webhook_secret = webhook_secret.encode("utf-8")
        self._currency = default_currency
        self._lock = threading.RLock()
        self._sessions: dict[str, CheckoutSession] = {}
        self._subscriptions: dict[str, Subscription] = {}
        self._invoices: dict[str, Invoice] = {}
        self._id_seq = 0

    # ----- helpers -----
    def _next_id(self, prefix: str) -> str:
        with self._lock:
            self._id_seq += 1
            return f"{prefix}_mock_{self._id_seq:08d}"

    def _sign(self, payload: bytes) -> str:
        return hmac.new(self._webhook_secret, payload, hashlib.sha256).hexdigest()

    # ----- API -----
    @with_resilience(
        provider="payment_mock",
        method="create_checkout_session",
        retry=RetryPolicy(max_retries=2, base_delay=0.1),
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
        sid = self._next_id("cs")
        total = sum(it.amount_cents * it.quantity for it in items)
        currency = items[0].currency or self._currency
        url = f"https://mock-payment.local/checkout/{sid}?amount={total}&cur={currency}"
        session = CheckoutSession(
            session_id=sid,
            url=url,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            provider=self.provider_name,
            raw={
                "items": [
                    {
                        "name": it.name,
                        "amount_cents": it.amount_cents,
                        "currency": it.currency,
                        "quantity": it.quantity,
                        "description": it.description,
                        "metadata": dict(it.metadata),
                    }
                    for it in items
                ],
                "customer": {
                    "customer_id": customer.customer_id,
                    "email": customer.email,
                    "name": customer.name,
                    "phone": customer.phone,
                    "metadata": dict(customer.metadata),
                },
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": metadata or {},
            },
        )
        with self._lock:
            self._sessions[sid] = session
        return session

    @with_resilience(
        provider="payment_mock",
        method="verify_webhook",
        retry=RetryPolicy(max_retries=0),
    )
    async def verify_webhook(self, payload: bytes | str, signature: str) -> WebhookEvent:
        if isinstance(payload, str):
            payload_bytes = payload.encode("utf-8")
        else:
            payload_bytes = payload
        expected = self._sign(payload_bytes)
        if not hmac.compare_digest(expected, signature or ""):
            raise AuthError(
                "webhook signature mismatch",
                provider=self.provider_name,
            )
        try:
            data = json.loads(payload_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise InvalidRequestError(f"invalid webhook payload: {exc}") from exc
        event_id = data.get("id") or self._next_id("evt")
        event_type = data.get("type") or "unknown"
        occurred_at_raw = data.get("occurred_at")
        if occurred_at_raw:
            occurred_at = datetime.fromisoformat(occurred_at_raw)
        else:
            occurred_at = datetime.now(timezone.utc)
        return WebhookEvent(
            event_id=event_id,
            event_type=event_type,
            provider=self.provider_name,
            occurred_at=occurred_at,
            data=data.get("data", {}),
            raw=data,
        )

    @with_resilience(
        provider="payment_mock",
        method="get_subscription",
        retry=RetryPolicy(max_retries=2),
    )
    async def get_subscription(self, subscription_id: str) -> Subscription:
        with self._lock:
            sub = self._subscriptions.get(subscription_id)
        if sub is None:
            raise InvalidRequestError(
                f"subscription {subscription_id} not found",
                provider=self.provider_name,
            )
        return sub

    @with_resilience(
        provider="payment_mock",
        method="cancel_subscription",
        retry=RetryPolicy(max_retries=2),
    )
    async def cancel_subscription(
        self,
        subscription_id: str,
        *,
        at_period_end: bool = True,
    ) -> None:
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
                sub.canceled_at = datetime.now(timezone.utc)

    @with_resilience(
        provider="payment_mock",
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
        currency = items[0].currency or self._currency
        invoice_id = self._next_id("inv")
        now = datetime.now(timezone.utc)
        invoice = Invoice(
            invoice_id=invoice_id,
            customer_id=customer.customer_id or self._next_id("cus"),
            amount_cents=amount,
            currency=currency,
            status="open",
            issued_at=now,
            due_at=now + timedelta(days=due_days),
            hosted_url=f"https://mock-payment.local/invoices/{invoice_id}",
            line_items=list(items),
            metadata=metadata or {},
        )
        with self._lock:
            self._invoices[invoice_id] = invoice
        return invoice

    # ----- 测试用辅助方法 -----
    def seed_subscription(self, subscription: Subscription) -> None:
        """测试前手动注入订阅(默认 active,本期末取消)."""
        with self._lock:
            self._subscriptions[subscription.subscription_id] = subscription

    def simulate_webhook(
        self,
        event_type: str,
        data: dict[str, object],
        *,
        occurred_at: datetime | None = None,
    ) -> tuple[bytes, str]:
        """构造合法 (payload, signature) 用于回调测试."""
        body = {
            "id": self._next_id("evt"),
            "type": event_type,
            "occurred_at": (occurred_at or datetime.now(timezone.utc)).isoformat(),
            "data": data,
        }
        payload = json.dumps(body, sort_keys=True).encode("utf-8")
        signature = self._sign(payload)
        return payload, signature