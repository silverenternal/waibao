"""Notify providers."""
from __future__ import annotations

from .base import NotifyMessage, NotifyProvider, NotifyResult
from .dingtalk_provider import DingTalkProvider
from .feishu_provider import FeishuProvider
from .mock_provider import (
    MOCK_NOTIFY_REGISTRY,
    MockDingTalkProvider,
    MockFeishuProvider,
    MockNotifyProvider,
    MockSMTPProvider,
    MockWebhookProvider,
    MockWeComProvider,
    get_mock_notify_provider,
)
from .smtp_provider import SMTPProvider
from .webhook_provider import WebhookProvider
from .wecom_provider import WeComProvider

__all__ = [
    "DingTalkProvider",
    "FeishuProvider",
    "MOCK_NOTIFY_REGISTRY",
    "MockDingTalkProvider",
    "MockFeishuProvider",
    "MockNotifyProvider",
    "MockSMTPProvider",
    "MockWebhookProvider",
    "MockWeComProvider",
    "NotifyMessage",
    "NotifyProvider",
    "NotifyResult",
    "SMTPProvider",
    "WeComProvider",
    "WebhookProvider",
    "get_mock_notify_provider",
]