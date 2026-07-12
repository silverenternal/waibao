"""Stripe 真实支付接入验证 (T1701).

默认 **跳过** — 需要 STRIPE_SECRET_KEY (测试模式 sk_test_...):

    export STRIPE_SECRET_KEY="sk_test_..."
    pytest -m real_api backend/providers/payment/tests/test_stripe_real.py

凭证申请: docs/REAL_API_SETUP.md (9 Stripe)
"""
from __future__ import annotations

import json
import os
import time

import pytest

from backend.providers.exceptions import AuthError
from backend.providers.payment.stripe import (
    StripeProvider,
    verify_stripe_signature,
)
from backend.providers.payment.types import Customer, LineItem


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not os.getenv("STRIPE_SECRET_KEY"),
        reason="STRIPE_SECRET_KEY 未设置 — 跳过 Stripe 真实 API 测试",
    ),
]


WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test_only")


@pytest.fixture
def provider():
    return StripeProvider(api_key=os.getenv("STRIPE_SECRET_KEY"))


@pytest.mark.asyncio
async def test_instantiate_with_real_key(provider):
    assert provider.api_key.startswith("sk_")


@pytest.mark.asyncio
async def test_create_checkout_session_real(provider):
    """真实创建 checkout session,获取跳转 URL."""
    items = [
        LineItem(
            name="Waibao Pro Monthly",
            amount_cents=9900,
            currency="usd",
            quantity=1,
        )
    ]
    customer = Customer(
        email="test+stripe@waibao.local",
        name="Waibao Test User",
    )
    session = await provider.create_checkout_session(
        items=items,
        customer=customer,
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
        metadata={"test_run_id": "stripe-001"},
    )
    assert session.session_id.startswith("cs_")
    assert session.url.startswith("https://checkout.stripe.com/")
    assert session.provider == "stripe"


def test_verify_webhook_signature_local():
    """签名校验 (本地构造 event,验证 HMAC-SHA256 一致)."""
    payload = json.dumps(
        {"id": "evt_test", "type": "checkout.session.completed", "data": {}}
    ).encode("utf-8")
    ts = int(time.time())
    sig = "t=" + str(ts) + ",v1=" + _sign(ts, payload, WEBHOOK_SECRET)
    event = verify_stripe_signature(payload, sig, secret=WEBHOOK_SECRET)
    assert event["type"] == "checkout.session.completed"


def test_verify_webhook_signature_invalid_raises():
    """错误签名应抛 AuthError."""
    payload = b'{"id":"evt_bad"}'
    sig = "t=1234567890,v1=deadbeef"
    with pytest.raises(AuthError):
        verify_stripe_signature(payload, sig, secret=WEBHOOK_SECRET)


def test_verify_webhook_signature_stale_timestamp():
    """过期时间戳应被拒绝."""
    payload = b'{"id":"evt_old"}'
    old_ts = int(time.time()) - 600  # 10 分钟前
    sig = f"t={old_ts},v1=irrelevant"
    with pytest.raises(AuthError) as exc_info:
        verify_stripe_signature(payload, sig, secret=WEBHOOK_SECRET)
    assert "tolerance" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _sign(ts: int, payload: bytes, secret: str) -> str:
    """直接复用 stripe.py 的内部签名函数."""
    import hashlib
    import hmac as hmac_lib

    signed = f"{ts}.".encode("utf-8") + payload
    return hmac_lib.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()