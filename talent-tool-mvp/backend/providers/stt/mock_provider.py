"""STT Mock Provider — 返回固定占位转写文字."""
from __future__ import annotations

from typing import Any

from .base import STTProvider, STTResult


class MockSTTProvider(STTProvider):
    """纯本地 mock,不发起任何网络请求."""

    provider_name = "mock"

    async def transcribe(
        self,
        audio: bytes,
        *,
        mime: str = "audio/mpeg",
        language: str = "auto",
        **kwargs: Any,
    ) -> STTResult:
        text = f"[mock-stt] bytes={len(audio)} mime={mime} lang={language}"
        return STTResult(
            text=text,
            language=language if language != "auto" else "en",
            duration=len(audio) / 16000.0,  # 估算时长 (16kHz mono)
            segments=[
                {"start": 0.0, "end": len(audio) / 16000.0, "text": text}
            ],
        )

    async def transcribe_url(
        self,
        url: str,
        *,
        language: str = "auto",
        **kwargs: Any,
    ) -> STTResult:
        text = f"[mock-stt] url={url} lang={language}"
        return STTResult(
            text=text,
            language=language if language != "auto" else "en",
            duration=1.0,
            segments=[{"start": 0.0, "end": 1.0, "text": text}],
        )