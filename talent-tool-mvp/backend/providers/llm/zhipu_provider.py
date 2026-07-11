"""智谱 GLM Provider.

智谱同时提供 OpenAI 兼容接口 (``base_url=https://open.bigmodel.cn/api/paas/v4``)
和自有的 ZhipuAI SDK。本实现优先使用 OpenAI 兼容协议 (复用 AsyncOpenAI 客户端),
依赖最少,行为与 OpenAI 一致。

继承 :class:`OpenAICompatibleProvider`,通过 ENV_KEY=``ZHIPU_API_KEY`` 读 key,
并把熔断/限流/cost/metrics 的 key 设为 ``zhipu`` 而非 ``openai``。
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar

from ..base import with_resilience
from .base import LLMResponse, Message, ToolCallResult, ToolDefinition
from .openai_provider import OpenAICompatibleProvider, map_openai_exception


class ZhipuProvider(OpenAICompatibleProvider):
    """智谱 GLM-4 系列 provider."""

    provider_name = "zhipu"
    ENV_KEY = "ZHIPU_API_KEY"
    DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
    DEFAULT_MODEL = "glm-4-flash"

    # 价格 (USD / 1M tokens),按智谱 bigmodel 公开价目。
    PRICING: ClassVar[dict[str, tuple[float, float]]] = {
        "glm-4-plus": (7.0, 7.0),
        "glm-4-air": (0.7, 0.7),
        "glm-4-airx": (1.0, 1.0),
        "glm-4-flash": (0.1, 0.1),
        "glm-4-long": (0.5, 0.5),
    }

    @with_resilience(provider="zhipu", method="chat", rate_per_sec=10.0, burst=20)
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
            raise map_openai_exception(exc, provider="zhipu") from exc
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
            raise map_openai_exception(exc, provider="zhipu") from exc
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