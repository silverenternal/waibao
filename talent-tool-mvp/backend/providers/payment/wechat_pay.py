"""T1405 — 微信支付 (JSAPI / Native / H5) Provider.

微信支付 V3 签名:
    sign = HMAC-SHA256(key, "{method}\n{url}\n{timestamp}\n{nonce}\n{body}\n")
    Authorization: WECHATPAY2-SHA256-RSA2048 mchid="..",nonce_str="..",
                   signature="..",timestamp="..",serial_no=".."

回调验签:
    1) 校验 timestamp 容差
    2) 从 header 取 signature / nonce / timestamp
    3) 用平台证书验证签名 (此处离线实现使用 merchant secret 模拟,生产应替换)

为保持完全可测,本实现提供离线/在线双模式 + 回调签名校验工具.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

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

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 微信 V3 签名工具
# ---------------------------------------------------------------------------
def _build_signing_string(
    method: str, url: str, timestamp: str, nonce: str, body: str
) -> str:
    return f"{method}\n{url}\n{timestamp}\n{nonce}\n{body}\n"


def wechat_v3_sign(
    *,
    method: str,
    url: str,
    body: str,
    secret: str,
    nonce: str | None = None,
    timestamp: str | None = None,
) -> dict[str, str]:
    """构造微信 V3 Authorization 头 (简化版)."""
    ts = timestamp or str(int(time.time()))
    nc = nonce or secrets.token_hex(8)
    signing = _build_signing_string(method.upper(), url, ts, nc, body)
    sig = hmac.new(
        secret.encode("utf-8"), signing.encode("utf-8"), hashlib.sha256
    ).digest()
    return {
        "timestamp": ts,
        "nonce_str": nc,
        "signature": base64.b64encode(sig).decode("ascii"),
    }


def verify_wechat_webhook_signature(
    *,
    timestamp: str,
    nonce: str,
    body: str,
    signature: str,
    secret: str,
    tolerance_seconds: int = 300,
) -> bool:
    """校验微信 V3 回调签名.

    timestamp 单位:秒. 返回 True 表示合法.
    """
    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise AuthError(f"invalid timestamp: {exc}", provider="wechat") from exc
    now = int(datetime.now(tz=timezone.utc).timestamp())
    if abs(now - ts) > tolerance_seconds:
        raise AuthError(
            "wechat webhook timestamp out of tolerance",
            provider="wechat",
            details={"tolerance_seconds": tolerance_seconds},
        )
    signing = f"{timestamp}\n{nonce}\n{body}\n"
    expected = base64.b64encode(
        hmac.new(
            secret.encode("utf-8"), signing.encode("utf-8"), hashlib.sha256
        ).digest()
    ).decode("ascii")
    if not hmac.compare_digest(expected, signature or ""):
        raise AuthError("wechat webhook signature mismatch", provider="wechat")
    return True


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------
class WeChatPayProvider(PaymentProvider):
    """微信支付 V3 (JSAPI / Native / H5).

    离线模式:
        用本地内存存储 checkout session / 订阅 / 发票;
        create_checkout_session 返回 weixin://wxpay/bizpayurl?pr=xxx 风格的 url;
        verify_webhook 使用 HMAC-SHA256 模拟回调签名.

    在线模式 (预留):
        mch_id + api_key 存在时,可对接 /v3/pay/transactions/native 等真实接口.
    """

    provider_name = "wechat"

    def __init__(
        self,
        *,
        mch_id: str | None = None,
        api_key: str | None = None,
        api_v3_key: str | None = None,
        webhook_secret: str | None = None,
        default_currency: str = "cny",
        trade_type: str = "NATIVE",
    ) -> None:
        self.mch_id = mch_id or ""
        self.api_key = api_key or ""
        self.api_v3_key = api_v3_key or secrets.token_hex(16)
        self.webhook_secret = webhook_secret or self.api_v3_key
        self._currency = default_currency.lower()
        self.trade_type = trade_type
        self._lock = threading.RLock()
        self._sessions: dict[str, CheckoutSession] = {}
        self._subscriptions: dict[str, Subscription] = {}
        self._invoices: dict[str, Invoice] = {}
        self._id_seq = 0

    def _next_id(self, prefix: str) -> str:
        with self._lock:
            self._id_seq += 1
            ts = int(datetime.now(tz=timezone.utc).timestamp())
            return f"{prefix}_{ts}_{self._id_seq:06d}"

    # ----- API -----
    @with_resilience(
        provider="payment_wechat",
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
        total = sum(it.amount_cents * it.quantity for it in items)
        currency = (items[0].currency or self._currency).lower()
        out_trade_no = self._next_id("wx")
        if self.trade_type == "JSAPI":
            url = f"weixin://wxpay/bizpayurl?pr={out_trade_no}"
        elif self.trade_type == "H5":
            url = f"https://wx.tenpay.com/cgi-bin/mmpayweb-bin/checkmweb?prepay_id={out_trade_no}"
        else:  # NATIVE
            url = f"weixin://wxpay/bizpayurl?pr={out_trade_no}"

        session = CheckoutSession(
            session_id=out_trade_no,
            url=url,
            expires_at=datetime.now(tz=timezone.utc) + timedelta(minutes=30),
            provider=self.provider_name,
            raw={
                "mch_id": self.mch_id,
                "out_trade_no": out_trade_no,
                "trade_type": self.trade_type,
                "total": total,
                "currency": currency,
                "items": [it.__dict__ for it in items],
                "customer": customer.__dict__,
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": metadata or {},
            },
        )
        with self._lock:
            self._sessions[out_trade_no] = session
        return session

    @with_resilience(
        provider="payment_wechat",
        method="verify_webhook",
        retry=RetryPolicy(max_retries=0),
    )
    async def verify_webhook(
        self, payload: bytes | str, signature: str
    ) -> WebhookEvent:
        """校验微信回调签名.

        signature 可为字符串 header "t=..,nonce=..,sig=.." (便于与 stripe 保持一致)
        或纯 hex (配合 payload 头的 X-Wechat-Timestamp / X-Wechat-Nonce).

        实际部署推荐 FastAPI Header 直接传 timestamp / nonce / signature 三个 header.
        为统一接口,这里接收单个 signature 字段:
            signature = "<base64-sig>"
        而 timestamp / nonce 嵌入到 payload 的 header 字段.
        """
        if isinstance(payload, str):
            payload_bytes = payload.encode("utf-8")
        else:
            payload_bytes = payload
        try:
            envelope = json.loads(payload_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise InvalidRequestError(f"invalid webhook payload: {exc}", provider="wechat") from exc

        # envelope 期望: { "header": {...}, "body": "...", "resource": {...} }
        header = envelope.get("header") or {}
        body_str = (
            envelope.get("body")
            if isinstance(envelope.get("body"), str)
            else json.dumps(envelope.get("body", {}), sort_keys=True)
        )
        ts = str(header.get("timestamp") or int(datetime.now(tz=timezone.utc).timestamp()))
        nonce = str(header.get("nonce") or "")
        verify_wechat_webhook_signature(
            timestamp=ts,
            nonce=nonce,
            body=body_str,
            signature=signature,
            secret=self.webhook_secret,
        )
        resource = envelope.get("resource") or {}
        cipher = resource.get("ciphertext") or ""
        # 简化: ciphertext 当作明文(生产应使用 api_v3_key 解密 AEAD_AES_256_GCM)
        try:
            decoded = json.loads(cipher) if cipher else {}
        except json.JSONDecodeError:
            decoded = {"raw": cipher}
        return WebhookEvent(
            event_id=str(header.get("id") or self._next_id("evt")),
            event_type=str(resource.get("event_type") or "TRANSACTION.SUCCESS"),
            provider=self.provider_name,
            occurred_at=datetime.now(tz=timezone.utc),
            data={
                "decoded": decoded,
                "out_trade_no": decoded.get("out_trade_no"),
                "transaction_id": decoded.get("transaction_id"),
                "result_code": decoded.get("result_code") or "SUCCESS",
                "amount": decoded.get("amount"),
                "metadata": resource.get("metadata") or {},
            },
            raw=envelope,
        )

    @with_resilience(
        provider="payment_wechat",
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
        provider="payment_wechat",
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
                sub.canceled_at = datetime.now(tz=timezone.utc)

    @with_resilience(
        provider="payment_wechat",
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
        inv_id = self._next_id("inv")
        now = datetime.now(tz=timezone.utc)
        invoice = Invoice(
            invoice_id=inv_id,
            customer_id=customer.customer_id or self._next_id("cus"),
            amount_cents=amount,
            currency=currency,
            status="open",
            issued_at=now,
            due_at=now + timedelta(days=due_days),
            hosted_url=f"https://pay.weixin.qq.com/invoice/{inv_id}",
            line_items=list(items),
            metadata=metadata or {},
        )
        with self._lock:
            self._invoices[inv_id] = invoice
        return invoice

    # ----- 测试辅助 -----
    def seed_subscription(self, subscription: Subscription) -> None:
        with self._lock:
            self._subscriptions[subscription.subscription_id] = subscription

    def make_signed_payload(
        self,
        *,
        event_type: str,
        out_trade_no: str,
        transaction_id: str | None = None,
        amount_cents: int | None = None,
        result_code: str = "SUCCESS",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[bytes, str, dict[str, str]]:
        """构造合法 (payload, signature, headers) 用于 webhook 测试."""
        ts = int(datetime.now(tz=timezone.utc).timestamp())
        nonce = secrets.token_hex(8)
        resource = {
            "event_type": event_type,
            "ciphertext": json.dumps(
                {
                    "out_trade_no": out_trade_no,
                    "transaction_id": transaction_id or self._next_id("wx"),
                    "result_code": result_code,
                    "amount": {"total": amount_cents or 0, "currency": "CNY"},
                    "metadata": metadata or {},
                },
                sort_keys=True,
            ),
        }
        envelope = {
            "header": {"id": self._next_id("evt"), "timestamp": ts, "nonce": nonce},
            "resource": resource,
            "body": "{}",  # 简化
        }
        payload = json.dumps(envelope, sort_keys=True).encode("utf-8")
        # 签名: over "{ts}\n{nonce}\n{body}\n"
        signing = f"{ts}\n{nonce}\n{{}}\n".encode("utf-8")
        sig = base64.b64encode(
            hmac.new(
                self.webhook_secret.encode("utf-8"), signing, hashlib.sha256
            ).digest()
        ).decode("ascii")
        headers = {
            "X-Wechatpay-Timestamp": str(ts),
            "X-Wechatpay-Nonce": nonce,
        }
        return payload, sig, headers


__all__ = ["WeChatPayProvider", "verify_wechat_webhook_signature", "wechat_v3_sign"]