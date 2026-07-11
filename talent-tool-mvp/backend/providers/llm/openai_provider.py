"""OpenAI Provider.

支持 gpt-4o / gpt-4o-mini / gpt-4-turbo / o1 系列,走原生 OpenAI SDK。

同时本文件还导出 ``OpenAICompatibleProvider`` 作为通用基类,
供其他走 OpenAI 兼容协议 (DeepSeek / Zhipu / Tongyi / Moonshot) 的供应商复用,
避免每家都重复写一遍 messages/tools 序列化和异常映射逻辑。
"""
from __future__ import annotations

import json
import os
from abc import abstractmethod
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from openai import AsyncOpenAI

from ..base import with_resilience
from ..exceptions import (
    AuthError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
    TimeoutError,
    UpstreamUnavailableError,
)
from .base import (
    LLMProvider,
    LLMResponse,
    Message,
    ToolCall,
    ToolCallResult,
    ToolDefinition,
    Usage,
)


# ---------------------------------------------------------------------------
# 通用辅助 (OpenAI 协议族共享)
# ---------------------------------------------------------------------------
def _dump_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _safe_json(s: str | None) -> dict[str, Any]:
    if not s:
        return {}
    try:
        result = json.loads(s)
        return result if isinstance(result, dict) else {"value": result}
    except Exception:
        return {"_raw": s}


def map_openai_exception(exc: Exception, *, provider: str) -> ProviderError:
    """将 openai SDK 抛的异常统一映射到 ProviderError.

    共享给所有 OpenAI 兼容 provider (DeepSeek/Zhipu/Tongyi/Moonshot)。
    """
    name = exc.__class__.__name__
    msg = str(exc)
    if "Authentication" in name or "401" in msg or "api_key" in msg.lower():
        return AuthError(msg, provider=provider)
    if "RateLimit" in name or "429" in msg:
        return RateLimitError(msg, provider=provider)
    if (
        "Timeout" in name
        or "ConnectError" in name
        or "ReadTimeout" in name
        or "Timeout" in msg
        or "ReadTimeout" in msg
        or "timed out" in msg.lower()
    ):
        return TimeoutError(msg, provider=provider)
    if (
        "Invalid" in name
        or "BadRequest" in name
        or "400" in msg
        or "404" in msg
        or "NotFound" in name
    ):
        return InvalidRequestError(msg, provider=provider)
    if "Quota" in name or "402" in msg or "insufficient_quota" in msg.lower():
        from ..exceptions import QuotaExceededError

        return QuotaExceededError(msg, provider=provider)
    return UpstreamUnavailableError(msg, provider=provider)


# ---------------------------------------------------------------------------
# OpenAI 兼容协议基类
# ---------------------------------------------------------------------------
class OpenAICompatibleProvider(LLMProvider):
    """所有走 OpenAI Chat Completions 协议 (含 base_url 兼容) 的供应商通用基类.

    子类只需声明:
        - ``provider_name``  (熔断/限流/cost/metrics 的 key)
        - ``ENV_KEY``        (读取 API key 的环境变量名, 如 OPENAI_API_KEY)
        - ``DEFAULT_BASE_URL``
        - ``DEFAULT_MODEL``
        - ``PRICING``        (≥3 个模型)
    """

    provider_name: ClassVar[str] = "openai_compatible"

    # 子类必须覆盖以下 ClassVar
    ENV_KEY: ClassVar[str] = "OPENAI_API_KEY"
    DEFAULT_BASE_URL: ClassVar[str | None] = None
    DEFAULT_MODEL: ClassVar[str] = "gpt-4o-mini"
    PRICING: ClassVar[dict[str, tuple[float, float]]] = {}

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
        super().__init__(**kwargs)
        self.api_key = api_key or os.getenv(self.ENV_KEY, "")
        if not self.api_key:
            raise InvalidRequestError(
                f"{self.ENV_KEY} is required for {self.provider_name}",
                provider=self.provider_name,
            )
        self.base_url = base_url or os.getenv(f"{self.ENV_KEY.rsplit('_API_KEY', 1)[0]}_BASE_URL") or self.DEFAULT_BASE_URL
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        self.default_model = default_model or self.DEFAULT_MODEL
        self._rate_per_sec = rate_per_sec
        self._burst = burst

    # ---- protocol ----
    @property
    def supported_models(self) -> list[str]:
        return list(self.PRICING.keys())

    @property
    def pricing(self) -> dict[str, tuple[float, float]]:
        return dict(self.PRICING)

    # ---- 共用: schema 序列化 ----
    @staticmethod
    def _serialize_messages(messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            item: dict[str, Any] = {"role": m.role, "content": m.content}
            if m.name:
                item["name"] = m.name
            if m.tool_call_id:
                item["tool_call_id"] = m.tool_call_id
            if m.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": _dump_json(tc.arguments)},
                    }
                    for tc in m.tool_calls
                ]
            out.append(item)
        return out

    @staticmethod
    def _serialize_tools(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    # ---- 共用: 响应解析 ----
    def _parse_completion(self, resp: Any) -> LLMResponse:
        choice = resp.choices[0]
        usage = Usage(
            prompt_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            completion_tokens=resp.usage.completion_tokens if resp.usage else 0,
            total_tokens=resp.usage.total_tokens if resp.usage else 0,
        )
        return LLMResponse(
            content=choice.message.content or "",
            model=resp.model,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
            tool_calls=[
                ToolCall(
                    id=tc.id,
                    name=tc.function.name or "",
                    arguments=_safe_json(tc.function.arguments),
                )
                for tc in (choice.message.tool_calls or [])
            ],
            raw=resp,
        )

    # ---- abstract (子类必须各自装饰 @with_resilience,key 用自己的 provider_name) ----
    @abstractmethod
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
    ) -> LLMResponse: ...


# ---------------------------------------------------------------------------
# OpenAI 官方
# ---------------------------------------------------------------------------
class OpenAIProvider(OpenAICompatibleProvider):
    """OpenAI 官方 (或任何把 base_url 改成自家域名的 OpenAI 兼容服务)。"""

    provider_name = "openai"
    ENV_KEY = "OPENAI_API_KEY"
    DEFAULT_BASE_URL = None  # 用 SDK 默认 (https://api.openai.com/v1)
    DEFAULT_MODEL = "gpt-4o-mini"

    PRICING: ClassVar[dict[str, tuple[float, float]]] = {
        "gpt-4o": (2.5, 10.0),
        "gpt-4o-mini": (0.15, 0.6),
        "gpt-4-turbo": (10.0, 30.0),
        "gpt-4-turbo-preview": (10.0, 30.0),
        "gpt-3.5-turbo": (0.5, 1.5),
        "o1-preview": (15.0, 60.0),
        "o1-mini": (3.0, 12.0),
    }

    @with_resilience(provider="openai", method="chat", rate_per_sec=10.0, burst=20)
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
        except ProviderError:
            raise
        except Exception as exc:
            raise map_openai_exception(exc, provider="openai") from exc
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
        except ProviderError:
            raise
        except Exception as exc:
            raise map_openai_exception(exc, provider="openai") from exc
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


__all__ = [
    "OpenAICompatibleProvider",
    "OpenAIProvider",
    "map_openai_exception",
]