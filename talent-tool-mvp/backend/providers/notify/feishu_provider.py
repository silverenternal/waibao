"""飞书机器人 Webhook Provider.

支持 text / post / interactive (消息卡片)。
签名校验:timestamp + sign (HMAC-SHA256, key=secret)。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Any

import httpx

from ..base import with_resilience
from ..exceptions import InvalidRequestError, ProviderError
from .base import NotifyMessage, NotifyProvider, NotifyResult


class FeishuProvider(NotifyProvider):
    """飞书群机器人."""

    channel = "feishu"

    def __init__(
        self,
        webhook: str | None = None,
        secret: str | None = None,
        *,
        rate_per_sec: float = 10.0,
        burst: int = 20,
    ) -> None:
        self.webhook = webhook or os.getenv("FEISHU_WEBHOOK", "")
        self.secret = secret or os.getenv("FEISHU_SECRET", "")
        if not self.webhook:
            raise InvalidRequestError(
                "FEISHU_WEBHOOK must be set", provider="feishu"
            )
        self._client = httpx.AsyncClient(timeout=15.0)
        self._rate_per_sec = rate_per_sec
        self._burst = burst

    def _sign(self) -> tuple[str, str]:
        if not self.secret:
            return "", ""
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        return timestamp, base64.b64encode(hmac_code).decode("ascii")

    @with_resilience(provider="feishu", method="send", rate_per_sec=10.0, burst=20)
    async def send(self, message: NotifyMessage) -> NotifyResult:
        payload: dict[str, Any] = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": message.subject or "通知",
                    }
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": message.html or message.body,
                    }
                ],
            },
        }
        if self.secret:
            ts, sign = self._sign()
            payload["timestamp"] = ts
            payload["sign"] = sign
        try:
            r = await self._client.post(self.webhook, json=payload)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as exc:
            raise _map_http(exc, "feishu") from exc
        except Exception as exc:
            raise ProviderError(str(exc), provider="feishu") from exc
        if data.get("code") not in (0, None):
            raise ProviderError(
                f"feishu error: {data}", provider="feishu"
            )
        return NotifyResult(
            success=True,
            channel=self.channel,
            message_id=data.get("data", {}).get("message_id") if isinstance(data.get("data"), dict) else None,
            raw=data,
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
