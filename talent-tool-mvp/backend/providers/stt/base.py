"""STT (Speech-to-Text) Provider 抽象基类."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class STTResult:
    """统一 STT 结果."""

    text: str
    language: str | None = None
    duration: float = 0.0
    segments: list[dict[str, Any]] | None = None
    raw: Any = None


class STTProvider(ABC):
    """语音转文字."""

    provider_name: str = "abstract"

    @abstractmethod
    async def transcribe(
        self,
        audio: bytes,
        *,
        mime: str = "audio/mpeg",
        language: str = "auto",
        **kwargs: Any,
    ) -> STTResult: ...

    @abstractmethod
    async def transcribe_url(
        self,
        url: str,
        *,
        language: str = "auto",
        **kwargs: Any,
    ) -> STTResult: ...
