"""OpenAI Embedding Provider."""
from __future__ import annotations

import os
from typing import Any

from openai import AsyncOpenAI

from ..base import with_resilience
from ..exceptions import InvalidRequestError, ProviderError
from .base import EmbeddingProvider, EmbeddingResult


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI text-embedding-3 系列."""

    provider_name = "openai"

    PRICING: dict[str, tuple[float, float]] = {
        "text-embedding-3-small": (0.02, 0.0),
        "text-embedding-3-large": (0.13, 0.0),
        "text-embedding-ada-002": (0.10, 0.0),
    }

    DIMENSIONS: dict[str, int] = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        default_model: str = "text-embedding-3-small",
        rate_per_sec: float = 50.0,
        burst: int = 100,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        if not self.api_key:
            raise InvalidRequestError(
                "OPENAI_API_KEY is required", provider="openai_embedding"
            )
        self.client = AsyncOpenAI(
            api_key=self.api_key, base_url=base_url or os.getenv("OPENAI_BASE_URL")
        )
        self.default_model = default_model
        self._rate_per_sec = rate_per_sec
        self._burst = burst

    @property
    def supported_models(self) -> list[str]:
        return list(self.PRICING.keys())

    @property
    def dimensions(self) -> int:
        return self.DIMENSIONS.get(self.default_model, 1536)

    @property
    def pricing(self) -> dict[str, tuple[float, float]]:
        return dict(self.PRICING)

    @with_resilience(provider="openai_embedding", method="embed", rate_per_sec=50.0, burst=100)
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
            model=resp.model,
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
    if "401" in msg or "api_key" in msg.lower():
        return AuthError(msg, provider="openai_embedding")
    if "429" in msg:
        return RateLimitError(msg, provider="openai_embedding")
    if "400" in msg:
        return InvalidRequestError(msg, provider="openai_embedding")
    return UpstreamUnavailableError(msg, provider="openai_embedding")
