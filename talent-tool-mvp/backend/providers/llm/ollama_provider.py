"""Ollama 本地 LLM Provider (v11.0 / T6101).

第三方大模型数据完全不允许离开甲方环境 —— Ollama 在甲方内网本地运行,
所有 prompt / completion / tool_call 全程不出网。

设计要点:
    1. Ollama 暴露 OpenAI 兼容的 ``/v1/chat/completions`` 接口
       (默认 ``http://ollama:11434/v1``),因此直接复用 ``AsyncOpenAI`` SDK,
       无需引入 ollama 官方 SDK。
    2. 本地模型 **无需 API key**。故意 **不继承** ``OpenAICompatibleProvider``
       (后者在 ``__init__`` 里硬性校验 ENV_KEY 存在),而是直接基于
       ``LLMProvider`` 抽象 + ``AsyncOpenAI(api_key="ollama", base_url=...)``。
    3. 默认模型 ``qwen2.5:7b-instruct`` (中文表现最好);
       备选 ``glm4:9b`` / ``llama3.1:8b``。
    4. base_url 从 ``OLLAMA_BASE_URL`` 读取,默认 ``http://ollama:11434``
       (provider 内部自动补 ``/v1``)。
    5. 复用 ``openai_provider.map_openai_exception`` 做异常映射,保证
       熔断 / 限流 / 重试 / 指标体系与其它 provider 一致。
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from openai import AsyncOpenAI

from ..base import with_resilience
from .base import (
    LLMProvider,
    LLMResponse,
    Message,
    ToolCall,
    ToolCallResult,
    ToolDefinition,
    Usage,
)
from .openai_provider import map_openai_exception

# Ollama 不计费 (本地自托管),pricing 全 0 —— 仍要给 calculate_cost 用。
_DEFAULT_PRICING: dict[str, tuple[float, float]] = {
    "qwen2.5:7b-instruct": (0.0, 0.0),
    "glm4:9b": (0.0, 0.0),
    "llama3.1:8b": (0.0, 0.0),
}


def _normalize_base_url(raw: str) -> str:
    """把任意 ``OLLAMA_BASE_URL`` 规范化成 ``.../v1`` 结尾 (OpenAI SDK 要 /v1).

    接受 ``http://ollama:11434`` / ``http://ollama:11434/`` /
    ``http://ollama:11434/v1`` 等写法。
    """
    url = raw.rstrip("/")
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


class OllamaProvider(LLMProvider):
    """Ollama 本地 LLM (OpenAI 兼容协议),数据全程不出甲方环境."""

    provider_name: ClassVar[str] = "ollama"

    # env / 默认值
    ENV_BASE_URL: ClassVar[str] = "OLLAMA_BASE_URL"
    DEFAULT_BASE_URL: ClassVar[str] = "http://ollama:11434"
    DEFAULT_MODEL: ClassVar[str] = "qwen2.5:7b-instruct"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        default_model: str | None = None,
        api_key: str | None = None,
        timeout: float = 120.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        raw = base_url or os.getenv(self.ENV_BASE_URL, "").strip() or self.DEFAULT_BASE_URL
        self.base_url = _normalize_base_url(raw)
        self.default_model = default_model or os.getenv("OLLAMA_MODEL", "").strip() or self.DEFAULT_MODEL
        # Ollama 本地服务不需要真实 key,但 openai SDK 要求非空字段,给个占位符。
        self.api_key = api_key or "ollama"
        self.timeout = float(timeout)
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

    # ---- protocol: supported_models / pricing ----
    @property
    def supported_models(self) -> list[str]:
        return list(_DEFAULT_PRICING.keys())

    @property
    def pricing(self) -> dict[str, tuple[float, float]]:
        return dict(_DEFAULT_PRICING)

    # ---- 共用: schema 序列化 (与 OpenAICompatibleProvider 等价) ----
    @staticmethod
    def _serialize_messages(messages: list[Message]) -> list[dict[str, Any]]:
        import json

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
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
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

    @staticmethod
    def _safe_json(s: str | None) -> dict[str, Any]:
        import json

        if not s:
            return {}
        try:
            result = json.loads(s)
            return result if isinstance(result, dict) else {"value": result}
        except Exception:  # noqa: BLE001
            return {"_raw": s}

    def _parse_completion(self, resp: Any) -> LLMResponse:
        choice = resp.choices[0]
        usage = Usage(
            prompt_tokens=getattr(resp.usage, "prompt_tokens", 0) if resp.usage else 0,
            completion_tokens=getattr(resp.usage, "completion_tokens", 0) if resp.usage else 0,
            total_tokens=getattr(resp.usage, "total_tokens", 0) if resp.usage else 0,
        )
        return LLMResponse(
            content=choice.message.content or "",
            model=getattr(resp, "model", self.default_model),
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
            tool_calls=[
                ToolCall(
                    id=getattr(tc, "id", "") or "",
                    name=tc.function.name or "",
                    arguments=self._safe_json(tc.function.arguments),
                )
                for tc in (choice.message.tool_calls or [])
            ],
            raw=resp,
        )

    # ---- chat ----
    @with_resilience(provider="ollama", method="chat", rate_per_sec=10.0, burst=20)
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
            raise map_openai_exception(exc, provider="ollama") from exc
        return self._parse_completion(resp)

    # ---- stream ----
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
            raise map_openai_exception(exc, provider="ollama") from exc
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    # ---- tool_call ----
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


__all__ = ["OllamaProvider", "_normalize_base_url"]
