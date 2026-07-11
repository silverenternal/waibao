"""企业微信群机器人 Webhook Provider.

支持 text / markdown 类型消息。
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from ..base import with_resilience
from ..exceptions import InvalidRequestError, ProviderError
from .base import NotifyMessage, NotifyProvider, NotifyResult


class WeComProvider(NotifyProvider):
    """企业微信群机器人."""

    channel = "wecom"

    def __init__(
        self,
        webhook: str | None = None,
        *,
        mentioned_list: list[str] | None = None,
        rate_per_sec: float = 10.0,
        burst: int = 20,
    ) -> None:
        self.webhook = webhook or os.getenv("WECOM_WEBHOOK", "")
        if not self.webhook:
            raise InvalidRequestError(
                "WECOM_WEBHOOK must be set", provider="wecom"
            )
        self.mentioned_list = mentioned_list or []
        self._client = httpx.AsyncClient(timeout=15.0)
        self._rate_per_sec = rate_per_sec
        self._burst = burst

    @with_resilience(provider="wecom", method="send", rate_per_sec=10.0, burst=20)
    async def send(self, message: NotifyMessage) -> NotifyResult:
        # markdown 类型支持 @ 提及
        payload: dict[str, Any] = {
            "msgtype": "markdown",
            "markdown": {
                "content": (message.subject and f"**{message.subject}**\n") or ""
                + (message.html or message.body),
            },
        }
        mentioned: list[str] = list(self.mentioned_list)
        if message.metadata and message.metadata.get("mentioned_list"):
            mentioned.extend(message.metadata["mentioned_list"])
        if mentioned:
            payload["markdown"]["mentioned_list"] = mentioned
        try:
            r = await self._client.post(self.webhook, json=payload)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as exc:
            raise _map_http(exc, "wecom") from exc
        except Exception as exc:
            raise ProviderError(str(exc), provider="wecom") from exc
        if data.get("errcode") not in (0, None):
            raise ProviderError(
                f"wecom error: {data}", provider="wecom"
            )
        return NotifyResult(
            success=True, channel=self.channel, raw=data
        )


def _map_http(exc: httpx.HTTPStatusError, provider: str) -> ProviderError:
    from ..exceptions import (
        AuthError,
        InvalidRequestError,
        RateLimitError,
        UpstreamUnavailableError,
    )

    code = exc.response.status_code
    msg = exc.response.text
    if code in (401, 403):
        return AuthError(msg, provider=provider)
    if code == 429:
        return RateLimitError(msg, provider=provider)
    if 400 <= code < 500:
        return InvalidRequestError(msg, provider=provider)
    return UpstreamUnavailableError(msg, provider=provider)
