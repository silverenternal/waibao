"""通义 Embedding Provider (text-embedding-v3).

DashScope 兼容 OpenAI 模式 (/compatible-mode/v1/embeddings)。
"""
from __future__ import annotations

import os
from typing import Any

from openai import AsyncOpenAI

from ..base import with_resilience
from ..exceptions import InvalidRequestError, ProviderError
from .base import EmbeddingProvider, EmbeddingResult


class TongyiEmbeddingProvider(EmbeddingProvider):
    """通义 text-embedding-v3 (默认 1024 维)."""

    provider_name = "tongyi"

    PRICING: dict[str, tuple[float, float]] = {
        "text-embedding-v3": (0.7, 0.0),
        "text-embedding-v2": (0.7, 0.0),
    }

    DIMENSIONS: dict[str, int] = {
        "text-embedding-v3": 1024,
        "text-embedding-v2": 1536,
    }

    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        default_model: str = "text-embedding-v3",
        rate_per_sec: float = 20.0,
        burst: int = 50,
    ) -> None:
        resolved_key = api_key or os.getenv("DASHSCOPE_API_KEY", "") or os.getenv(
            "TONGYI_API_KEY", ""
        )
        if not resolved_key:
            raise InvalidRequestError(
                "DASHSCOPE_API_KEY is required", provider="tongyi_embedding"
            )
        self.client = AsyncOpenAI(
            api_key=resolved_key,
            base_url=base_url or os.getenv("DASHSCOPE_BASE_URL", self.DEFAULT_BASE_URL),
        )
        self.default_model = default_model
        self._rate_per_sec = rate_per_sec
        self._burst = burst

    @property
    def supported_models(self) -> list[str]:
        return list(self.PRICING.keys())

    @property
    def dimensions(self) -> int:
        return self.DIMENSIONS.get(self.default_model, 1024)

    @property
    def pricing(self) -> dict[str, tuple[float, float]]:
        return dict(self.PRICING)

    @with_resilience(provider="tongyi_embedding", method="embed", rate_per_sec=20.0, burst=50)
    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> EmbeddingResult:
        model = model or self.default_model
        try:
            resp = await self.client.embeddings.create(
                model=model, input=texts, **kwargs
            )
        except Exception as exc:
            raise _map_exception(exc) from exc
        vectors = [d.embedding for d in resp.data]
        return EmbeddingResult(
            vectors=vectors,
            model=model,
            dimensions=len(vectors[0]) if vectors else 0,
            usage_tokens=resp.usage.total_tokens if resp.usage else 0,
        )

    async def embed_one(
        self,
        text: str,
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> list[float]:
        result = await self.embed([text], model=model, **kwargs)
        return result.vectors[0] if result.vectors else []


def _map_exception(exc: Exception) -> ProviderError:
    from ..exceptions import (
        AuthError,
        InvalidRequestError,
        RateLimitError,
        UpstreamUnavailableError,
    )

    msg = str(exc)
    if "401" in msg or "InvalidApiKey" in msg:
        return AuthError(msg, provider="tongyi_embedding")
    if "429" in msg or "Quota" in msg:
        return RateLimitError(msg, provider="tongyi_embedding")
    if "400" in msg:
        return InvalidRequestError(msg, provider="tongyi_embedding")
    return UpstreamUnavailableError(msg, provider="tongyi_embedding")
