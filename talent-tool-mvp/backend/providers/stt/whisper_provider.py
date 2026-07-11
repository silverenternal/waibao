"""OpenAI Whisper STT Provider.

走 OpenAI Audio Transcriptions API,支持 mp3/mp4/wav/webm 等格式。
"""
from __future__ import annotations

import os
from typing import Any

from openai import AsyncOpenAI

from ..base import with_resilience
from ..exceptions import InvalidRequestError, ProviderError
from .base import STTProvider, STTResult


class WhisperProvider(STTProvider):
    """OpenAI Whisper (whisper-1)."""

    provider_name = "whisper"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        default_model: str = "whisper-1",
        rate_per_sec: float = 5.0,
        burst: int = 10,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        if not self.api_key:
            raise InvalidRequestError(
                "OPENAI_API_KEY is required", provider="whisper"
            )
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=base_url or os.getenv("OPENAI_BASE_URL"),
        )
        self.default_model = default_model
        self._rate_per_sec = rate_per_sec
        self._burst = burst

    @with_resilience(provider="whisper", method="transcribe", rate_per_sec=5.0, burst=10)
    async def transcribe(
        self,
        audio: bytes,
        *,
        mime: str = "audio/mpeg",
        language: str = "auto",
        **kwargs: Any,
    ) -> STTResult:
        try:
            # openai sdk 接受 (filename, content) tuple
            resp = await self.client.audio.transcriptions.create(
                model=self.default_model,
                file=("audio", audio),
                language=None if language == "auto" else language,
                response_format="verbose_json",
                **kwargs,
            )
        except Exception as exc:
            raise _map(exc) from exc
        return STTResult(
            text=resp.text,
            language=getattr(resp, "language", None),
            duration=float(getattr(resp, "duration", 0.0) or 0.0),
            segments=[s.model_dump() for s in (resp.segments or [])] or None,
            raw=resp,
        )

    async def transcribe_url(
        self, url: str, *, language: str = "auto", **kwargs: Any
    ) -> STTResult:
        import httpx

        async with httpx.AsyncClient(timeout=120.0) as c:
            r = await c.get(url)
            r.raise_for_status()
            data = r.content
        return await self.transcribe(data, language=language, **kwargs)


def _map(exc: Exception) -> ProviderError:
    from ..exceptions import (
        AuthError,
        InvalidRequestError,
        RateLimitError,
        UpstreamUnavailableError,
    )

    msg = str(exc)
    if "401" in msg or "api_key" in msg.lower():
        return AuthError(msg, provider="whisper")
    if "429" in msg:
        return RateLimitError(msg, provider="whisper")
    if "400" in msg:
        return InvalidRequestError(msg, provider="whisper")
    return UpstreamUnavailableError(msg, provider="whisper")
