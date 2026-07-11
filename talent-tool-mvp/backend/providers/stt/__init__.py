"""STT providers."""
from __future__ import annotations

from .aliyun_stt import AliyunSTTProvider
from .base import STTProvider, STTResult
from .mock_provider import MockSTTProvider
from .whisper_provider import WhisperProvider

__all__ = [
    "AliyunSTTProvider",
    "MockSTTProvider",
    "STTProvider",
    "STTResult",
    "WhisperProvider",
]