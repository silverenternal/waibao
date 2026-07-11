"""DeepSeek Provider.

DeepSeek 提供 OpenAI 兼容的 chat/completions 接口,
通过 ``base_url=https://api.deepseek.com`` (OpenAI SDK 会自动拼 /v1)。

继承 :class:`OpenAICompatibleProvider`,只声明自己的 provider_name /
ENV_KEY / DEFAULT_BASE_URL / DEFAULT_MODEL / PRICING,以及用自身 provider_name
作为 key 装饰 chat 与 stream_chat,确保熔断/限流/cost/metrics 各自独立。
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar

from ..base import with_resilience
from .base import LLMResponse, Message, ToolCallResult, ToolDefinition
from .openai_provider import OpenAICompatibleProvider, map_openai_exception


class DeepSeekProvider(OpenAICompatibleProvider):
    """DeepSeek (deepseek-chat / deepseek-reasoner 等) provider."""

    provider_name = "deepseek"
    ENV_KEY = "DEEPSEEK_API_KEY"
    DEFAULT_BASE_URL = "https://api.deepseek.com"
    DEFAULT_MODEL = "deepseek-chat"

    # 价格 (USD / 1M tokens),按 DeepSeek 官方公开价目。
    PRICING: ClassVar[dict[str, tuple[float, float]]] = {
        "deepseek-chat": (0.14, 0.28),        # V3 系列 cache miss
        "deepseek-reasoner": (0.55, 2.19),    # R1 系列
        "deepseek-coder": (0.14, 0.28),       # 代码专用
    }

    @with_resilience(provider="deepseek", method="chat", rate_per_sec=10.0, burst=20)
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
        params: dict[str, Any] = {
            "model": model,
            "messages": self._serialize_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            params["tools"] = self._serialize_tools(tools)
        if response_format:
            params["response_format"] = response_format
        params.update(kwargs)
        try:
            resp = await self.client.chat.completions.create(**params)
        except Exception as exc:
            raise map_openai_exception(exc, provider="deepseek") from exc
        return self._parse_completion(resp)

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
        params: dict[str, Any] = {
            "model": model,
            "messages": self._serialize_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        params.update(kwargs)
        try:
            stream = await self.client.chat.completions.create(**params)
        except Exception as exc:
            raise map_openai_exception(exc, provider="deepseek") from exc
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

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
            tool_choice="auto",
            **kwargs,
        )
        return ToolCallResult(
            content=resp.content,
            tool_calls=resp.tool_calls,
            finish_reason=resp.finish_reason,
        )
