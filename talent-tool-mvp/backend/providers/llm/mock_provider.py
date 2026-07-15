"""LLM Mock Provider (v11.0 默认 fallback 到 ollama).

设计动机 (T6101):
    甲方要求「第三方大模型数据完全不允许离开甲方环境」。因此 MockLLMProvider
    不再是纯离线 stub —— 它优先 **fallback 到本地 OllamaProvider**,只有当
    Ollama 不可达 (离线 / 未启动) 时,才回退到旧的启发式 mock 响应,保证开发
    环境无需任何配置也能拿到合理回复。

    行为选择由环境变量 ``LLM_PROVIDER`` 控制:
      - 显式 ``mock``  → 走本类 (先 ollama,不通则启发式)
      - 未设置 / ``ollama`` → registry 直接返回 OllamaProvider (不经本类)
      - 其它 → 对应真实 provider

    ``WAIBAO_PROVIDER_MOCK=1`` 之外的 mock 调用仍受 registry 的 mock gate
    约束;本类本身只是「带 ollama fallback 的开发态 provider」。
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from .base import (
    LLMProvider,
    LLMResponse,
    Message,
    ToolCallResult,
    ToolDefinition,
    Usage,
)

logger = logging.getLogger(__name__)


class MockLLMProvider(LLMProvider):
    """本地优先 provider: 先 Ollama,不通则启发式 mock."""

    provider_name = "mock"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # 延迟导入避免循环依赖 + 让测试能在无 ollama 环境运行
        self._ollama: LLMProvider | None = None
        self._ollama_unavailable = False
        try:
            from .ollama_provider import OllamaProvider

            # fallback 探测用短超时 (3s),Ollama 离线时立即退回启发式,不拖慢调用。
            self._ollama = OllamaProvider(timeout=3.0)
        except Exception:  # noqa: BLE001
            self._ollama = None

        # 快速 TCP 预探测 (≤2s):避免每次调用都被 with_resilience 的重试
        # (3 次指数退避) 卡住。Ollama 不通时直接标记不可用,走启发式。
        if self._ollama is not None and not self._ollama_reachable():
            self._ollama_unavailable = True

        # 复用 runtime.LLMClient 的启发式路由 —— 仅作 Ollama 不可用时的兜底。
        try:
            from agents.runtime import LLMClient
        except ImportError:
            try:
                from backend.agents.runtime import LLMClient  # type: ignore[no-redef]
            except ImportError:  # pragma: no cover - 极端 fallback
                LLMClient = None  # type: ignore[assignment]
        self._runtime_client_cls = LLMClient
        # _skip_provider_resolve=True 避免无限递归
        if LLMClient is not None:
            self._client = LLMClient(
                openai_client=None, model="mock-model", _skip_provider_resolve=True
            )
        else:  # pragma: no cover
            self._client = None

    def _ollama_reachable(self) -> bool:
        """1.5s 内 TCP 探测 OLLAMA_BASE_URL;不通返回 False."""
        import socket
        from urllib.parse import urlparse

        url = urlparse(getattr(self._ollama, "base_url", "") or "")
        if not url.hostname:
            return False
        port = url.port or (443 if url.scheme == "https" else 80)
        try:
            with socket.create_connection((url.hostname, port), timeout=1.5):
                return True
        except OSError:
            return False

    # ---- protocol: supported_models / pricing ----
    @property
    def supported_models(self) -> list[str]:
        if self._ollama is not None and not self._ollama_unavailable:
            return self._ollama.supported_models + ["mock-model"]
        return ["mock-model"]

    @property
    def pricing(self) -> dict[str, tuple[float, float]]:
        return {"mock-model": (0.0, 0.0)}

    # ---- helpers ----
    @staticmethod
    def _to_runtime_messages(messages: list[Message]) -> list[dict[str, Any]]:
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

    def _heuristic(self, messages: list[Message]) -> str:
        if self._client is None:  # pragma: no cover
            return "（本地 mock 响应:Ollama 与 runtime 均不可用）"
        return self._client._mock_response(self._to_runtime_messages(messages))

    async def _via_ollama(self, coro_factory: Any) -> Any | None:
        """尝试用 ollama 执行 ``coro_factory()``;不通返回 None 并标记不可用."""
        if self._ollama is None or self._ollama_unavailable:
            return None
        try:
            return await coro_factory()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ollama 不可用,MockLLMProvider 回退启发式: %s", exc)
            self._ollama_unavailable = True
            return None

    # ---- chat ----
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
        resp = await self._via_ollama(
            lambda: self._ollama.chat(  # type: ignore[union-attr]
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                response_format=response_format,
                **kwargs,
            )
        )
        if resp is not None:
            return resp
        text = self._heuristic(messages)
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
        if self._ollama is not None and not self._ollama_unavailable:
            try:
                async for token in self._ollama.stream_chat(  # type: ignore[union-attr]
                    messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                ):
                    yield token
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("Ollama stream 不可用,回退启发式: %s", exc)
                self._ollama_unavailable = True

        resp = await self.chat(
            messages, model=model, temperature=temperature, max_tokens=max_tokens, **kwargs
        )
        for ch in resp.content:
            yield ch

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
        result = await self._via_ollama(
            lambda: self._ollama.tool_call(  # type: ignore[union-attr]
                messages,
                tools,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
        )
        if result is not None:
            return result
        return ToolCallResult(content=None, tool_calls=[], finish_reason="stop")
