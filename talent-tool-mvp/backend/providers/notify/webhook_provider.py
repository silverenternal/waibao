"""通用自定义 Webhook Provider.

业务方自定义 URL + 模板,适合任何 HTTP 接收端 (Bark / Server酱 / 自建网关)。
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from ..base import with_resilience
from ..exceptions import InvalidRequestError, ProviderError
from .base import NotifyMessage, NotifyProvider, NotifyResult


class WebhookProvider(NotifyProvider):
    """通用 Webhook (默认 channel=webhook,可在配置中覆盖为 bark/serverchan 等)."""

    channel = "webhook"

    def __init__(
        self,
        url: str | None = None,
        *,
        method: str = "POST",
        headers: dict[str, str] | None = None,
        template: str | None = None,
        rate_per_sec: float = 10.0,
        burst: int = 20,
    ) -> None:
        self.url = url or os.getenv("WEBHOOK_URL", "")
        self.method = (method or os.getenv("WEBHOOK_METHOD", "POST")).upper()
        self.headers = headers or _parse_headers(os.getenv("WEBHOOK_HEADERS", ""))
        self.template = template or os.getenv("WEBHOOK_TEMPLATE", "json")
        if not self.url:
            raise InvalidRequestError(
                "WEBHOOK_URL must be set", provider="webhook"
            )
        self._client = httpx.AsyncClient(timeout=15.0)
        self._rate_per_sec = rate_per_sec
        self._burst = burst

    @with_resilience(provider="webhook", method="send", rate_per_sec=10.0, burst=20)
    async def send(self, message: NotifyMessage) -> NotifyResult:
        if self.template == "json":
            payload: Any = {
                "subject": message.subject,
                "body": message.body,
                "html": message.html,
                "to": message.to,
                "metadata": message.metadata or {},
            }
            r = await self._client.request(
                self.method, self.url, json=payload, headers=self.headers
            )
        else:  # form
            form: dict[str, str] = {
                "subject": message.subject or "",
                "body": message.body or "",
            }
            r = await self._client.request(
                self.method, self.url, data=form, headers=self.headers
            )
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _map_http(exc, "webhook") from exc
        return NotifyResult(
            success=True,
            channel=self.channel,
            raw=r.text[:1000],
        )


def _parse_headers(raw: str) -> dict[str, str]:
    if not raw:
        return {}
    headers: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip()] = v.strip()
    return headers


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
