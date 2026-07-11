"""Anthropic Claude Provider.

使用 anthropic SDK。messages API 风格与 OpenAI 不同,需做 schema 转换。
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from ..base import with_resilience
from ..exceptions import InvalidRequestError
from .base import (
    LLMProvider,
    LLMResponse,
    Message,
    ToolCall,
    ToolCallResult,
    ToolDefinition,
    Usage,
)

try:
    from anthropic import AsyncAnthropic
except Exception:  # pragma: no cover - anthropic SDK 为可选依赖
    AsyncAnthropic = None  # type: ignore[assignment]


class AnthropicProvider(LLMProvider):
    """Anthropic Claude 系列."""

    provider_name = "anthropic"

    PRICING: dict[str, tuple[float, float]] = {
        "claude-3-5-sonnet-latest": (3.0, 15.0),
        "claude-3-5-haiku-latest": (0.8, 4.0),
        "claude-3-opus-latest": (15.0, 75.0),
    }

    def __init__(
        self,
        api_key: str | None = None,
        *,
        default_model: str = "claude-3-5-sonnet-latest",
        rate_per_sec: float = 5.0,
        burst: int = 10,
    ) -> None:
        super().__init__()
        if AsyncAnthropic is None:
            raise InvalidRequestError(
                "anthropic SDK 未安装,请 pip install anthropic",
                provider="anthropic",
            )
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not self.api_key:
            raise InvalidRequestError("ANTHROPIC_API_KEY is required", provider="anthropic")
        self.client = AsyncAnthropic(api_key=self.api_key)
        self.default_model = default_model
        self._rate_per_sec = rate_per_sec
        self._burst = burst

    @property
    def supported_models(self) -> list[str]:
        return list(self.PRICING.keys())

    @property
    def pricing(self) -> dict[str, tuple[float, float]]:
        return dict(self.PRICING)

    @staticmethod
    def _convert_messages(messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
        """Claude 接受 system 作为顶层参数,其他为 messages."""
        system_parts: list[str] = []
        converted: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                if m.content:
                    system_parts.append(m.content)
                continue
            if m.role == "tool":
                converted.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": m.tool_call_id or "",
                                "content": m.content,
                            }
                        ],
                    }
                )
                continue
            converted.append({"role": m.role, "content": m.content})
        return ("\n\n".join(system_parts) if system_parts else None), converted

    def _convert_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            }
            for t in tools
        ]

    @with_resilience(provider="anthropic", method="chat", rate_per_sec=5.0, burst=10)
    async def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: list[ToolDefinition] | None = None,
        response_format: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        model = model or self.default_model
        system, msgs = self._convert_messages(messages)
        params: dict[str, Any] = {
            "model": model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            params["system"] = system
        if tools:
            params["tools"] = self._convert_tools(tools)
        params.update(kwargs)
        try:
            resp = await self.client.messages.create(**params)
        except Exception as exc:
            raise _map_anthropic_exception(exc) from exc

        # 拼装 content blocks
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )
        usage = Usage(
            prompt_tokens=resp.usage.input_tokens,
            completion_tokens=resp.usage.output_tokens,
            total_tokens=resp.usage.input_tokens + resp.usage.output_tokens,
        )
        return LLMResponse(
            content="".join(text_parts),
            model=resp.model,
            finish_reason=resp.stop_reason or "stop",
            usage=usage,
            tool_calls=tool_calls,
            raw=resp,
        )

    async def stream_chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        model = model or self.default_model
        system, msgs = self._convert_messages(messages)
        try:
            async with self.client.messages.stream(
                model=model,
                messages=msgs,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system or "",
                **kwargs,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as exc:
            raise _map_anthropic_exception(exc) from exc

    async def tool_call(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> ToolCallResult:
        resp = await self.chat(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            **kwargs,
        )
        return ToolCallResult(
            content=resp.content,
            tool_calls=resp.tool_calls,
            finish_reason=resp.finish_reason,
        )


def _map_anthropic_exception(exc: Exception) -> Exception:
    from ..exceptions import (
        AuthError,
        InvalidRequestError,
        ProviderError,
        RateLimitError,
        TimeoutError,
        UpstreamUnavailableError,
    )

    name = exc.__class__.__name__
    msg = str(exc)
    if "Authentication" in name or "401" in msg:
        return AuthError(msg, provider="anthropic")
    if "RateLimit" in name or "429" in msg:
        return RateLimitError(msg, provider="anthropic")
    if "Timeout" in name:
        return TimeoutError(msg, provider="anthropic")
    if "InvalidRequest" in name or "400" in msg:
        return InvalidRequestError(msg, provider="anthropic")
    if isinstance(exc, ProviderError):
        return exc
    return UpstreamUnavailableError(msg, provider="anthropic")
