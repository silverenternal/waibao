"""LLM Mock Provider — 复用 backend.agents.runtime.LLMClient._mock_response 的启发式逻辑.

设计动机:
    registry 在 LLM_PROVIDER=mock 时,直接返回本类实例.
    本类不实现任何真实 LLM 调用,但要求响应格式必须严格符合 LLMProvider 协议,
    并尽可能复用现有 _mock_response 的 agent-aware 路由(情感/职业/画像 等),
    这样开发环境不需要 API key 也能拿到合理的回复。
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from .base import (
    LLMProvider,
    LLMResponse,
    Message,
    ToolCallResult,
    Usage,
)


class MockLLMProvider(LLMProvider):
    """纯本地 mock 实现,无网络请求."""

    provider_name = "mock"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # 复用 runtime.LLMClient 的启发式路由能力 — 延迟导入避免循环依赖
        try:
            from agents.runtime import LLMClient
        except ImportError:
            from backend.agents.runtime import LLMClient  # type: ignore[no-redef]

        # 关键:用 _skip_provider_resolve=True 标志跳过 provider 解析,
        # 避免 LLMClient(openai_client=None) 再次触发 MockLLMProvider -> LLMClient -> ...
        # 的无限递归。_mock_response 是纯函数,不依赖 provider,所以这里可以直接绕过。
        self._client = LLMClient(openai_client=None, model="mock-model", _skip_provider_resolve=True)

    # ---- protocol: supported_models / pricing ----
    @property
    def supported_models(self) -> list[str]:
        return ["mock-model"]

    @property
    def pricing(self) -> dict[str, tuple[float, float]]:
        # (input_usd_per_1m, output_usd_per_1m) — mock 免费
        return {"mock-model": (0.0, 0.0)}

    # ---- helpers ----
    @staticmethod
    def _to_runtime_messages(messages: list[Message]) -> list[dict[str, Any]]:
        """把 LLMProvider 的 dataclass Message 转成 runtime 期望的 dict."""
        out: list[dict[str, Any]] = []
        for m in messages:
            out.append(
                {
                    "role": m.role,
                    "content": m.content,
                    **({"name": m.name} if m.name else {}),
                    **({"tool_call_id": m.tool_call_id} if m.tool_call_id else {}),
                }
            )
        return out

    # ---- chat ----
    async def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: list | None = None,
        response_format: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        text = self._client._mock_response(self._to_runtime_messages(messages))
        # 模拟粗略 token 数,便于上层 cost 估算
        prompt_tokens = sum(len(m.content) for m in messages) // 2
        completion_tokens = len(text) // 2
        return LLMResponse(
            content=text,
            model="mock-model",
            finish_reason="stop",
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

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
        resp = await self.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens, **kwargs)
        for ch in resp.content:
            yield ch

    # ---- tool_call ----
    async def tool_call(
        self,
        messages: list[Message],
        tools: list,
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> ToolCallResult:
        return ToolCallResult(
            content=None,
            tool_calls=[],
            finish_reason="stop",
        )