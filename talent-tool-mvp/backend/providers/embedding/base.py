"""Embedding Provider 抽象基类."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class EmbeddingResult:
    """统一的 embedding 返回结果."""

    vectors: list[list[float]]
    model: str
    dimensions: int
    usage_tokens: int = 0


class EmbeddingProvider(ABC):
    """文本转向量."""

    provider_name: str = "abstract"

    @property
    @abstractmethod
    def supported_models(self) -> list[str]:
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """默认模型输出维度."""

    @property
    @abstractmethod
    def pricing(self) -> dict[str, tuple[float, float]]:
        """(usd_per_1m_tokens_input, _)."""

    @abstractmethod
    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
        **kwargs: object,
    ) -> EmbeddingResult:
        """批量 embed."""

    @abstractmethod
    async def embed_one(
        self,
        text: str,
        *,
        model: str | None = None,
        **kwargs: object,
    ) -> list[float]:
        """单条 embed,方便调用方."""
