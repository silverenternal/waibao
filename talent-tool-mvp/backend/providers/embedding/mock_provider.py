"""Embedding Mock Provider — 用 hash 生成稳定可复现的伪向量.

设计动机:
    - 无 API key 时,registry 自动 fallback 到本类
    - 向量可复现 (相同输入 -> 相同输出),便于本地做语义缓存测试
"""
from __future__ import annotations

import hashlib
import math
from typing import Any

from .base import EmbeddingProvider, EmbeddingResult


class MockEmbeddingProvider(EmbeddingProvider):
    """基于 SHA-256 hash 的可复现 mock embedding."""

    provider_name = "mock"
    _DIM = 16  # mock 维度,远小于真实模型但足够占位

    @property
    def supported_models(self) -> list[str]:
        return ["mock-embed"]

    @property
    def dimensions(self) -> int:
        return self._DIM

    @property
    def pricing(self) -> dict[str, tuple[float, float]]:
        return {"mock-embed": (0.0, 0.0)}

    @staticmethod
    def _text_to_vec(text: str, dim: int) -> list[float]:
        """把 text 哈希成 dim 维单位向量."""
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # 把哈希字节展成 dim 个 float in [-1, 1]
        raw = [((b - 128) / 128.0) for b in h]
        vec = (raw * ((dim // len(raw)) + 1))[:dim]
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> EmbeddingResult:
        vectors = [self._text_to_vec(t, self._DIM) for t in texts]
        return EmbeddingResult(
            vectors=vectors,
            model="mock-embed",
            dimensions=self._DIM,
            usage_tokens=sum(len(t) for t in texts),
        )

    async def embed_one(
        self,
        text: str,
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> list[float]:
        return self._text_to_vec(text, self._DIM)