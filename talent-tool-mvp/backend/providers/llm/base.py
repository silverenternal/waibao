"""LLM Provider 抽象基类.

所有 LLM 供应商都必须实现 LLMProvider 接口。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal


Role = Literal["system", "user", "assistant", "tool", "function"]


@dataclass(slots=True)
class Message:
    """统一的消息结构."""

    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list["ToolCall"] | None = None


@dataclass(slots=True)
class ToolDefinition:
    """OpenAI 风格的 tool schema."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolCall:
    """模型请求的工具调用."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolCallResult:
    """工具调用结果汇总."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"


@dataclass(slots=True)
class Usage:
    """token 用量."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(slots=True)
class LLMResponse:
    """统一的 LLM 响应."""

    content: str
    model: str
    finish_reason: str = "stop"
    usage: Usage = field(default_factory=Usage)
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None


class LLMProvider(ABC):
    """LLM 供应商抽象基类."""

    provider_name: str = "abstract"

    def __init__(self, **kwargs: Any) -> None:
        self._extra = kwargs

    @property
    @abstractmethod
    def supported_models(self) -> list[str]:
        """该 provider 支持的模型 ID 列表."""

    @property
    @abstractmethod
    def pricing(self) -> dict[str, tuple[float, float]]:
        """{model: (input_usd_per_1m, output_usd_per_1m)}."""

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
    ) -> LLMResponse:
        """非流式对话."""

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """流式对话,逐 token yield 文本片段."""

    @abstractmethod
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
        """强制工具调用,模型必须从 tools 中选择一个或多个调用."""

    def calculate_cost(self, model: str, usage: Usage) -> float:
        """根据 pricing 表算 USD 成本,未命中则 0."""
        price = self.pricing.get(model)
        if not price:
            return 0.0
        in_price, out_price = price
        return (usage.prompt_tokens * in_price + usage.completion_tokens * out_price) / 1_000_000


def message_from_dict(d: dict[str, Any]) -> Message:
    """便捷构造: dict -> Message."""
    return Message(
        role=d["role"],
        content=d.get("content", ""),
        name=d.get("name"),
        tool_call_id=d.get("tool_call_id"),
        tool_calls=[ToolCall(**tc) for tc in d.get("tool_calls", []) or []] or None,
    )
