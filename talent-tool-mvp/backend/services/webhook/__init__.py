"""Webhook 事件分发模块 (T802 / T804)."""
from __future__ import annotations

from .dispatcher import WebhookDispatcher, get_webhook_dispatcher, set_webhook_dispatcher
from .fire import fire_webhook
from .signer import (
    SignatureError,
    compute_signature,
    generate_secret,
    verify_signature,
)
from .types import (
    DeliveryRecord,
    DeliveryStatus,
    WebhookConfig,
    WebhookEvent,
    WebhookPayload,
)

__all__ = [
    "DeliveryRecord",
    "DeliveryStatus",
    "SignatureError",
    "WebhookConfig",
    "WebhookDispatcher",
    "WebhookEvent",
    "WebhookPayload",
    "compute_signature",
    "fire_webhook",
    "generate_secret",
    "get_webhook_dispatcher",
    "set_webhook_dispatcher",
    "verify_signature",
]
