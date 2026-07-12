"""MockPaymentProvider 单元测试."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.providers.payment import (
    CheckoutSession,
    Customer,
    Invoice,
    LineItem,
    Subscription,
    WebhookEvent,
)
from backend.providers.payment.mock import MockPaymentProvider


@pytest.fixture()
def provider() -> MockPaymentProvider:
    return MockPaymentProvider(webhook_secret="test-secret")


@pytest.mark.asyncio
async def test_create_checkout_session_returns_url(provider: MockPaymentProvider) -> None:
    items = [LineItem(name="Pro Plan", amount_cents=2900, quantity=1)]
    session = await provider.create_checkout_session(
        items=items,
        customer=Customer(email="u@example.com"),
        success_url="https://app/success",
        cancel_url="https://app/cancel",
    )
    assert isinstance(session, CheckoutSession)
    assert session.session_id.startswith("cs_mock_")
    assert session.url.startswith("https://mock-payment.local/checkout/")
    assert session.expires_at is not None


@pytest.mark.asyncio
async def test_create_checkout_session_rejects_empty(provider: MockPaymentProvider) -> None:
    from backend.providers.exceptions import InvalidRequestError

    with pytest.raises(InvalidRequestError):
        await provider.create_checkout_session(
            items=[],
            customer=Customer(),
            success_url="x",
            cancel_url="y",
        )


@pytest.mark.asyncio
async def test_verify_webhook_success_and_failure(provider: MockPaymentProvider) -> None:
    payload, sig = provider.simulate_webhook(
        event_type="checkout.session.completed",
        data={"session_id": "cs_test"},
    )
    event = await provider.verify_webhook(payload, sig)
    assert isinstance(event, WebhookEvent)
    assert event.event_type == "checkout.session.completed"
    assert event.data["session_id"] == "cs_test"

    # 错误签名应抛 AuthError
    from backend.providers.exceptions import AuthError

    with pytest.raises(AuthError):
        await provider.verify_webhook(payload, sig + "bad")


@pytest.mark.asyncio
async def test_subscription_lifecycle(provider: MockPaymentProvider) -> None:
    sub = Subscription(
        subscription_id="sub_test_001",
        customer_id="cus_test_001",
        status="active",
        plan_id="pro",
    )
    provider.seed_subscription(sub)
    got = await provider.get_subscription("sub_test_001")
    assert got.plan_id == "pro"
    # at_period_end 取消
    await provider.cancel_subscription("sub_test_001", at_period_end=True)
    again = await provider.get_subscription("sub_test_001")
    assert again.cancel_at_period_end is True
    # 立即取消
    await provider.cancel_subscription("sub_test_001", at_period_end=False)
    again = await provider.get_subscription("sub_test_001")
    assert again.status == "canceled"


@pytest.mark.asyncio
async def test_create_invoice(provider: MockPaymentProvider) -> None:
    items = [
        LineItem(name="Resume Parsing", amount_cents=500),
        LineItem(name="Job Posting", amount_cents=2000, quantity=2),
    ]
    invoice = await provider.create_invoice(
        customer=Customer(customer_id="cus_inv_001", email="b@example.com"),
        items=items,
        due_days=15,
    )
    assert isinstance(invoice, Invoice)
    assert invoice.amount_cents == 500 + 2000 * 2
    assert invoice.currency == "USD"
    assert invoice.due_at is not None
    assert invoice.hosted_url is not None