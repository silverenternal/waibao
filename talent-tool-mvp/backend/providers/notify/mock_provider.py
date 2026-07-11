"""Notify Mock Provider — 5 通道占位实现 (smtp/dingtalk/feishu/wecom/webhook).

设计动机:
    - 单元测试 / 本地开发时 registry 自动 fallback
    - 每个 channel 必须返回 success=True + 唯一 message_id,便于上层做 idempotent
"""
from __future__ import annotations

import uuid
from typing import Any

from .base import NotifyMessage, NotifyProvider, NotifyResult


class MockNotifyProvider(NotifyProvider):
    """通用 mock,channel 通过构造参数切换."""

    provider_name = "mock"

    def __init__(self, channel: str = "mock", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # 即使父类有 channel 类属性,这里覆盖为实例属性 (允许 5 种 channel)
        self.channel = channel

    async def send(self, message: NotifyMessage) -> NotifyResult:
        return NotifyResult(
            success=True,
            channel=self.channel,
            message_id=f"mock-{self.channel}-{uuid.uuid4().hex[:12]}",
            error=None,
            raw={
                "subject": message.subject,
                "recipients": list(message.to),
                "body_len": len(message.body),
            },
        )


# 5 个通道的具体子类,只为让 channel 字段正确 (factory 用)
class MockSMTPProvider(MockNotifyProvider):
    channel = "smtp"


class MockDingTalkProvider(MockNotifyProvider):
    channel = "dingtalk"


class MockFeishuProvider(MockNotifyProvider):
    channel = "feishu"


class MockWeComProvider(MockNotifyProvider):
    channel = "wecom"


class MockWebhookProvider(MockNotifyProvider):
    channel = "webhook"


# 所有 channel 的注册表 (用于 registry 自动挑选对应 mock 子类)
MOCK_NOTIFY_REGISTRY: dict[str, type[MockNotifyProvider]] = {
    "smtp": MockSMTPProvider,
    "dingtalk": MockDingTalkProvider,
    "feishu": MockFeishuProvider,
    "wecom": MockWeComProvider,
    "webhook": MockWebhookProvider,
}


def get_mock_notify_provider(channel: str) -> MockNotifyProvider:
    """根据 channel 返回对应的 mock notify provider.

    未识别的 channel 退回到通用 MockNotifyProvider,避免 KeyError。
    """
    cls = MOCK_NOTIFY_REGISTRY.get(channel, MockNotifyProvider)
    return cls(channel=channel)