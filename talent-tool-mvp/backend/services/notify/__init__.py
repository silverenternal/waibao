"""通知服务子包 (T104).

包含:
- dispatcher: 统一调度器 (单通道/多通道并发推送)
- templates: 4 类业务通知模板 (jinja2)
"""
from __future__ import annotations

from .dispatcher import (
    ChannelResult,
    DispatchOutcome,
    NotifyDispatcher,
    dispatch,
    dispatch_multi,
    get_dispatcher,
)
from .templates import (
    NotificationTemplate,
    NotificationType,
    render_template,
)

__all__ = [
    "ChannelResult",
    "DispatchOutcome",
    "NotificationTemplate",
    "NotificationType",
    "NotifyDispatcher",
    "dispatch",
    "dispatch_multi",
    "get_dispatcher",
    "render_template",
]