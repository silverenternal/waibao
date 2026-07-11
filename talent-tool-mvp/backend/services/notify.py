"""多通道推送通知服务 (兼容层,委托给 notify.dispatcher).

历史: 早期版本每个通道各写一份 stub.
当前: 转发到 ``services.notify.dispatcher.NotifyDispatcher``,
由后者通过 ``providers.registry`` 拿到真正的 provider 实现 (mock 或真实 SMTP/IM).
新增通道无需修改此文件 —— 在 ``get_notify_provider`` registry 中注册即可.
"""
from __future__ import annotations

import logging
from typing import Optional

from .notify.dispatcher import (
    DispatchOutcome,
    NotifyDispatcher,
    dispatch,
    dispatch_multi,
    get_dispatcher,
    reset_dispatcher,
    set_dispatcher,
)
from .notify.templates import (
    NotificationTemplate,
    NotificationType,
    render_template,
)

logger = logging.getLogger("recruittech.services.notify")


async def push(
    channel: str,
    user_id: str,
    title: str,
    content: str,
    payload: Optional[dict] = None,
) -> bool:
    """统一推送入口 (兼容旧签名).

    委托给 :func:`services.notify.dispatcher.dispatch`,
    返回值语义保持一致 (成功/跳过 -> True; provider 实际失败 -> False).
    """
    return await dispatch(
        channel=channel,
        user_id=user_id,
        title=title,
        content=content,
        payload=payload,
    )


async def push_multi(
    channels: list[str],
    user_id: str,
    title: str,
    content: str,
    payload: Optional[dict] = None,
) -> DispatchOutcome:
    """多通道并发推送 (T104 新增)."""
    return await dispatch_multi(
        channels=channels,
        user_id=user_id,
        title=title,
        content=content,
        payload=payload,
    )


__all__ = [
    "DispatchOutcome",
    "NotificationTemplate",
    "NotificationType",
    "NotifyDispatcher",
    "dispatch",
    "dispatch_multi",
    "get_dispatcher",
    "push",
    "push_multi",
    "render_template",
    "reset_dispatcher",
    "set_dispatcher",
]