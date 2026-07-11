"""通义千问 (DashScope) Provider.

阿里云 DashScope 提供 OpenAI 兼容模式
(``base_url=https://dashscope.aliyuncs.com/compatible-mode/v1``),
直接复用 AsyncOpenAI 即可。

继承 :class:`OpenAICompatibleProvider`,把熔断/限流/cost/metrics 的 key
设为 ``tongyi``,同时兼容两个常见环境变量名 (TONGYI_API_KEY / DASHSCOPE_API_KEY)。
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from ..base import with_resilience
from .base import LLMResponse, Message, ToolCallResult, ToolDefinition
from .openai_provider import OpenAICompatibleProvider, map_openai_exception


class TongyiProvider(OpenAICompatibleProvider):
    """阿里云通义千问 Qwen 系列 provider."""

    provider_name = "tongyi"
    ENV_KEY = "TONGYI_API_KEY"
    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DEFAULT_MODEL = "qwen-turbo"

    # 价格 (USD / 1M tokens),按 DashScope 公开价目折算 (人民币换算近似)。
    PRICING: ClassVar[dict[str, tuple[float, float]]] = {
        "qwen-max": (20.0, 60.0),
        "qwen-plus": (2.0, 6.0),
        "qwen-turbo": (0.3, 0.6),
        "qwen-long": (0.5, 2.0),
    }

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        default_model: str | None = None,
        rate_per_sec: float = 10.0,
        burst: int = 20,
        **kwargs: Any,
    ) -> None:
        if not api_key:
            api_key = os.getenv("TONGYI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        if not base_url:
            base_url = os.getenv("TONGYI_BASE_URL") or os.getenv("DASHSCOPE_BASE_URL")
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            default_model=default_model,
            rate_per_sec=rate_per_sec,
            burst=burst,
            **kwargs,
        )

    @with_resilience(provider="tongyi", method="chat", rate_per_sec=10.0, burst=20)
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
            raise map_openai_exception(exc, provider="tongyi") from exc
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
            raise map_openai_exception(exc, provider="tongyi") from exc
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
