"""钉钉自定义机器人 Webhook Provider.

支持 text / link / markdown / actionCard / feedCard。
签名模式:timestamp + sign。
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


class DingTalkProvider(NotifyProvider):
    """钉钉群机器人."""

    channel = "dingtalk"

    def __init__(
        self,
        webhook: str | None = None,
        secret: str | None = None,
        *,
        rate_per_sec: float = 10.0,
        burst: int = 20,
    ) -> None:
        self.webhook = webhook or os.getenv("DINGTALK_WEBHOOK", "")
        self.secret = secret or os.getenv("DINGTALK_SECRET", "")
        if not self.webhook:
            raise InvalidRequestError(
                "DINGTALK_WEBHOOK must be set", provider="dingtalk"
            )
        self._client = httpx.AsyncClient(timeout=15.0)
        self._rate_per_sec = rate_per_sec
        self._burst = burst

    def _sign(self) -> tuple[str, str]:
        if not self.secret:
            return "", ""
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = base64.b64encode(hmac_code).decode("ascii")
        return timestamp, sign

    @with_resilience(provider="dingtalk", method="send", rate_per_sec=10.0, burst=20)
    async def send(self, message: NotifyMessage) -> NotifyResult:
        url = self.webhook
        if self.secret:
            ts, sign = self._sign()
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}timestamp={ts}&sign={sign}"
        payload: dict[str, Any] = {
            "msgtype": "markdown" if message.html else "text",
            "markdown" if message.html else "text": {
                "title": message.subject or "通知",
                "text": message.html or message.body,
            },
        }
        # at 人
        if message.metadata and message.metadata.get("atMobiles"):
            payload["at"] = {
                "atMobiles": message.metadata["atMobiles"],
                "isAtAll": False,
            }
        try:
            r = await self._client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as exc:
            raise _map_http(exc, "dingtalk") from exc
        except Exception as exc:
            raise ProviderError(str(exc), provider="dingtalk") from exc
        if data.get("errcode") not in (0, None):
            raise ProviderError(
                f"dingtalk error: {data}", provider="dingtalk"
            )
        return NotifyResult(
            success=True,
            channel=self.channel,
            message_id=str(data.get("messageId")) if data.get("messageId") else None,
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
