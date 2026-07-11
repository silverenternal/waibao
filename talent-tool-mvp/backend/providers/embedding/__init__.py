"""Embedding providers."""
from __future__ import annotations

from .base import EmbeddingProvider, EmbeddingResult
from .mock_provider import MockEmbeddingProvider
from .openai_embedding import OpenAIEmbeddingProvider
from .tongyi_embedding import TongyiEmbeddingProvider
from .zhipu_embedding import ZhipuEmbeddingProvider

__all__ = [
    "EmbeddingProvider",
    "EmbeddingResult",
    "MockEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "TongyiEmbeddingProvider",
    "ZhipuEmbeddingProvider",
]