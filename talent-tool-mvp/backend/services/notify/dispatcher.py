"""通知统一调度器 (T104).

核心职责:
1. 通过 ``providers.registry.get_notify_provider(channel)`` 获取对应通道的 provider.
2. 单通道推送 ``dispatch()`` —— 兼容旧 ``services.notify.push`` 调用.
3. 多通道并发推送 ``dispatch_multi()`` —— 用 ``asyncio.gather`` 并行发送.
4. 接收 ``NotificationTemplate`` 或裸 dict 载荷,统一归一为 ``NotifyMessage``.
5. 用户偏好过滤:从 ``notify_preferences`` 表读取用户在每个 channel 的开关,
   关闭的 channel 跳过 (由 ``preferences_lookup`` 回调注入,便于测试).
6. 失败隔离:某个通道失败不影响其他通道;所有结果聚合到 ``DispatchOutcome``.

设计要点:
- 不在 dispatcher 内做重试/限流 (Provider 内部已通过 ``with_resilience`` 装饰).
- ``get_dispatcher()`` 懒加载单例,允许测试时通过 ``reset_dispatcher`` 隔离.
- ``DispatchOutcome.success`` 含义: 至少有一个通道成功 (或全空 -> False).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable

from providers.notify.base import NotifyMessage, NotifyResult
from providers.registry import get_notify_provider

from .templates import NotificationTemplate, NotificationType

logger = logging.getLogger("recruittech.services.notify.dispatcher")


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ChannelResult:
    """单通道推送结果."""

    channel: str
    success: bool
    message_id: str | None = None
    error: str | None = None
    skipped: bool = False  # 用户偏好关闭 / 通道未启用


@dataclass(slots=True)
class DispatchOutcome:
    """多通道聚合结果."""

    results: list[ChannelResult] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """至少一个通道真正成功 (非 skipped)."""
        return any(r.success for r in self.results)

    @property
    def failed_channels(self) -> list[str]:
        return [r.channel for r in self.results if not r.success and not r.skipped]

    @property
    def skipped_channels(self) -> list[str]:
        return [r.channel for r in self.results if r.skipped]

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "channels": list(self.channels),
            "results": [
                {
                    "channel": r.channel,
                    "success": r.success,
                    "message_id": r.message_id,
                    "error": r.error,
                    "skipped": r.skipped,
                }
                for r in self.results
            ],
            "failed_channels": self.failed_channels,
            "skipped_channels": self.skipped_channels,
        }


# 类型: 偏好查询回调 (user_id, channel) -> bool (True=允许发送)
PreferencesLookup = Callable[[str, str], Awaitable[bool]]


async def _default_preferences_lookup(user_id: str, channel: str) -> bool:
    """默认实现:不做过滤,所有通道都允许.

    生产环境由 admin_notify API 注册的实现注入 (查询 notify_preferences 表).
    """
    return True


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class NotifyDispatcher:
    """统一通知调度器 (单例)."""

    def __init__(
        self,
        *,
        preferences_lookup: PreferencesLookup | None = None,
        provider_factory: Callable[[str], Any] | None = None,
    ) -> None:
        """初始化调度器.

        Args:
            preferences_lookup: 用户偏好查询回调; ``None`` 表示允许全部.
            provider_factory: provider 工厂 (默认走 ``get_notify_provider``);
                仅测试时注入.
        """
        self._preferences_lookup: PreferencesLookup = (
            preferences_lookup or _default_preferences_lookup
        )
        self._provider_factory: Callable[[str], Any] = (
            provider_factory or get_notify_provider
        )

    # ---- 公共 API ----

    async def dispatch(
        self,
        channel: str,
        user_id: str,
        title: str,
        content: str,
        payload: dict[str, Any] | None = None,
        *,
        recipients: list[str] | None = None,
    ) -> bool:
        """单通道推送 (兼容旧 ``services.notify.push`` 签名).

        Args:
            channel: 通道名 (smtp/dingtalk/feishu/wecom/webhook/web).
            user_id: 接收人 ID.
            title: 标题.
            content: 正文.
            payload: 透传给 provider 的额外 metadata (html/attachments/atMobiles).
            recipients: 显式收件人列表 (为空时回退到 ``[user_id]``).

        Returns:
            True 表示通道推送成功或被偏好跳过 (视为软成功);
            False 表示 provider 实际失败.
        """
        outcome = await self._dispatch_one(
            channel=channel,
            user_id=user_id,
            subject=title,
            body=content,
            payload=payload,
            recipients=recipients,
        )
        return outcome.success or outcome.skipped

    async def dispatch_multi(
        self,
        channels: Iterable[str],
        user_id: str,
        title: str,
        content: str,
        payload: dict[str, Any] | None = None,
        *,
        recipients: list[str] | None = None,
    ) -> DispatchOutcome:
        """多通道并发推送.

        Args:
            channels: 通道名列表 (会去重 + 过滤空字符串).
            user_id: 接收人 ID.
            title: 标题.
            content: 正文.
            payload: 透传 metadata.
            recipients: 显式收件人列表.

        Returns:
            ``DispatchOutcome`` 聚合所有通道的结果.
        """
        unique_channels = [c for c in dict.fromkeys(channels) if c]
        if not unique_channels:
            return DispatchOutcome(channels=[])

        tasks = [
            self._dispatch_one(
                channel=ch,
                user_id=user_id,
                subject=title,
                body=content,
                payload=payload,
                recipients=recipients,
            )
            for ch in unique_channels
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        channel_results: list[ChannelResult] = []
        for ch, res in zip(unique_channels, results):
            if isinstance(res, Exception):
                logger.exception("[notify-dispatcher] channel=%s crashed", ch, exc_info=res)
                channel_results.append(
                    ChannelResult(channel=ch, success=False, error=str(res))
                )
            else:
                channel_results.append(res)

        return DispatchOutcome(
            results=channel_results,
            channels=list(unique_channels),
        )

    async def dispatch_template(
        self,
        template: NotificationTemplate,
        channels: Iterable[str] | str,
        user_id: str,
        *,
        recipients: list[str] | None = None,
        extra_payload: dict[str, Any] | None = None,
    ) -> DispatchOutcome:
        """便捷方法:渲染好的模板 + 通道列表 -> 一次性推送.

        模板的 html/subject 会自动合并到 payload.
        """
        payload: dict[str, Any] = {
            "html": template.html,
            "metadata": dict(template.meta),
        }
        if extra_payload:
            payload.update(extra_payload)

        # 如果调用方没传 recipients,使用模板里登记的 default_recipients
        effective_recipients = recipients
        if not effective_recipients:
            default_rcpts = template.meta.get("default_recipients") if template.meta else None
            if default_rcpts:
                effective_recipients = list(default_rcpts)

        if isinstance(channels, str):
            result = await self._dispatch_one(
                channel=channels,
                user_id=user_id,
                subject=template.subject,
                body=template.body,
                payload=payload,
                recipients=effective_recipients,
            )
            return DispatchOutcome(results=[result], channels=[result.channel])

        return await self.dispatch_multi(
            channels=channels,
            user_id=user_id,
            title=template.subject,
            content=template.body,
            payload=payload,
            recipients=effective_recipients,
        )

    async def send_event(
        self,
        ntype: NotificationType,
        context: dict[str, Any],
        channels: Iterable[str] | str,
        user_id: str,
        *,
        recipients: list[str] | None = None,
    ) -> DispatchOutcome:
        """一站式入口: 渲染模板 + 推送到多通道.

        等价于 ``render_template`` + ``dispatch_template`` 的组合.
        """
        # 局部导入避免循环
        from .templates import render_template

        template = render_template(
            ntype,
            context=context,
            recipients=recipients,
        )
        return await self.dispatch_template(
            template=template,
            channels=channels,
            user_id=user_id,
            recipients=recipients,
        )

    # ---- 内部 ----

    async def _dispatch_one(
        self,
        *,
        channel: str,
        user_id: str,
        subject: str,
        body: str,
        payload: dict[str, Any] | None,
        recipients: list[str] | None,
    ) -> ChannelResult:
        """单通道完整流程: 偏好检查 -> 取 provider -> 发送 -> 记录结果."""
        # 1) 偏好过滤
        try:
            allowed = await self._preferences_lookup(user_id, channel)
        except Exception as exc:
            logger.warning(
                "[notify-dispatcher] preferences lookup failed user=%s channel=%s: %s",
                user_id,
                channel,
                exc,
            )
            # 偏好查询失败时,默认允许发送 (不要因为偏好的 bug 而丢消息)
            allowed = True

        if not allowed:
            logger.info(
                "[notify-dispatcher] skipped user=%s channel=%s (preference off)",
                user_id,
                channel,
            )
            return ChannelResult(channel=channel, success=False, skipped=True)

        # 2) 解析 payload
        html: str | None = None
        attachments = None
        metadata: dict[str, Any] | None = None
        if payload:
            html = payload.get("html")
            attachments = payload.get("attachments")
            metadata = payload.get("metadata") or payload.get("meta")

        # 3) 构造 NotifyMessage
        to_list = list(recipients) if recipients else [user_id]
        message = NotifyMessage(
            subject=subject,
            body=body,
            html=html,
            to=to_list,
            attachments=attachments,
            metadata=metadata,
        )

        # 4) 获取 provider 并发送
        try:
            provider = self._provider_factory(channel)
        except Exception as exc:
            logger.error(
                "[notify-dispatcher] no provider for channel=%s: %s", channel, exc
            )
            return ChannelResult(channel=channel, success=False, error=f"no provider: {exc}")

        try:
            result: NotifyResult = await provider.send(message)
        except Exception as exc:
            logger.exception(
                "[notify-dispatcher] send failed channel=%s user=%s", channel, user_id
            )
            return ChannelResult(channel=channel, success=False, error=str(exc))

        if not result.success:
            return ChannelResult(
                channel=channel,
                success=False,
                error=result.error or "provider returned failure",
            )

        return ChannelResult(
            channel=channel,
            success=True,
            message_id=result.message_id,
        )


# ---------------------------------------------------------------------------
# 模块级单例 + 便捷函数
# ---------------------------------------------------------------------------


_dispatcher: NotifyDispatcher | None = None


def get_dispatcher() -> NotifyDispatcher:
    """获取全局 dispatcher 单例 (懒加载)."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = NotifyDispatcher()
    return _dispatcher


def set_dispatcher(dispatcher: NotifyDispatcher | None) -> None:
    """替换/清空全局 dispatcher (主要用于测试或运行时注入偏好查询)."""
    global _dispatcher
    _dispatcher = dispatcher


def reset_dispatcher() -> None:
    """测试用: 清除全局单例."""
    set_dispatcher(None)


async def dispatch(
    channel: str,
    user_id: str,
    title: str,
    content: str,
    payload: dict[str, Any] | None = None,
    *,
    recipients: list[str] | None = None,
) -> bool:
    """模块级便捷入口: 单通道推送."""
    return await get_dispatcher().dispatch(
        channel=channel,
        user_id=user_id,
        title=title,
        content=content,
        payload=payload,
        recipients=recipients,
    )


async def dispatch_multi(
    channels: Iterable[str],
    user_id: str,
    title: str,
    content: str,
    payload: dict[str, Any] | None = None,
    *,
    recipients: list[str] | None = None,
) -> DispatchOutcome:
    """模块级便捷入口: 多通道并发推送."""
    return await get_dispatcher().dispatch_multi(
        channels=channels,
        user_id=user_id,
        title=title,
        content=content,
        payload=payload,
        recipients=recipients,
    )


__all__ = [
    "ChannelResult",
    "DispatchOutcome",
    "NotifyDispatcher",
    "PreferencesLookup",
    "dispatch",
    "dispatch_multi",
    "get_dispatcher",
    "reset_dispatcher",
    "set_dispatcher",
]