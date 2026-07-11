"""月之暗面 Kimi (Moonshot) Provider.

Moonshot 提供 OpenAI 兼容协议,base_url=https://api.moonshot.cn/v1。
直接复用 AsyncOpenAI 客户端即可。

继承 :class:`OpenAICompatibleProvider`,把熔断/限流/cost/metrics 的 key
设为 ``moonshot``。
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar

from ..base import with_resilience
from .base import LLMResponse, Message, ToolCallResult, ToolDefinition
from .openai_provider import OpenAICompatibleProvider, map_openai_exception


class MoonshotProvider(OpenAICompatibleProvider):
    """Kimi (Moonshot) 系列 provider."""

    provider_name = "moonshot"
    ENV_KEY = "MOONSHOT_API_KEY"
    DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"
    DEFAULT_MODEL = "moonshot-v1-8k"

    # 价格 (USD / 1M tokens),按 Moonshot 公开价目 (¥换算近似)。
    PRICING: ClassVar[dict[str, tuple[float, float]]] = {
        "moonshot-v1-8k": (1.0, 1.0),
        "moonshot-v1-32k": (2.0, 2.0),
        "moonshot-v1-128k": (5.0, 5.0),
        "moonshot-v1-auto": (2.0, 2.0),
    }

    @with_resilience(provider="moonshot", method="chat", rate_per_sec=5.0, burst=10)
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
            raise map_openai_exception(exc, provider="moonshot") from exc
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
            raise map_openai_exception(exc, provider="moonshot") from exc
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
