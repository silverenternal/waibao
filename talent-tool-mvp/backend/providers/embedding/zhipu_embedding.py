"""智谱 Embedding Provider (embedding-2)."""
from __future__ import annotations

import os
from typing import Any

import httpx

from ..base import with_resilience
from ..exceptions import InvalidRequestError, ProviderError
from .base import EmbeddingProvider, EmbeddingResult


class ZhipuEmbeddingProvider(EmbeddingProvider):
    """智谱 embedding-2 (1024 维)."""

    provider_name = "zhipu"

    PRICING: dict[str, tuple[float, float]] = {
        "embedding-2": (0.5, 0.0),
    }

    DEFAULT_MODEL = "embedding-2"
    DEFAULT_DIM = 1024
    ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/embeddings"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        default_model: str = DEFAULT_MODEL,
        rate_per_sec: float = 20.0,
        burst: int = 50,
    ) -> None:
        self.api_key = api_key or os.getenv("ZHIPU_API_KEY", "")
        if not self.api_key:
            raise InvalidRequestError(
                "ZHIPU_API_KEY is required", provider="zhipu_embedding"
            )
        self.base_url = base_url or os.getenv("ZHIPU_BASE_URL", self.ENDPOINT)
        self.default_model = default_model
        self._client = httpx.AsyncClient(timeout=30.0)
        self._rate_per_sec = rate_per_sec
        self._burst = burst

    @property
    def supported_models(self) -> list[str]:
        return list(self.PRICING.keys())

    @property
    def dimensions(self) -> int:
        return self.DEFAULT_DIM

    @property
    def pricing(self) -> dict[str, tuple[float, float]]:
        return dict(self.PRICING)

    @with_resilience(provider="zhipu_embedding", method="embed", rate_per_sec=20.0, burst=50)
    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> EmbeddingResult:
        model = model or self.default_model
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {"model": model, "input": texts}
        payload.update(kwargs)
        try:
            r = await self._client.post(self.base_url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as exc:
            raise _map_http_error(exc, "zhipu_embedding") from exc
        except Exception as exc:
            raise ProviderError(str(exc), provider="zhipu_embedding") from exc

        vectors = [d["embedding"] for d in data.get("data", [])]
        usage = data.get("usage", {})
        return EmbeddingResult(
            vectors=vectors,
            model=model,
            dimensions=len(vectors[0]) if vectors else 0,
            usage_tokens=usage.get("total_tokens", 0),
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


def _map_http_error(exc: httpx.HTTPStatusError, provider: str) -> ProviderError:
    from ..exceptions import (
        AuthError,
        InvalidRequestError,
        RateLimitError,
        UpstreamUnavailableError,
    )

    code = exc.response.status_code
    msg = exc.response.text
    if code in (401, 403):
        return AuthError(msg, provider=provider)
    if code == 429:
        return RateLimitError(msg, provider=provider)
    if 400 <= code < 500:
        return InvalidRequestError(msg, provider=provider)
    return UpstreamUnavailableError(msg, provider=provider)
