"""OCR Provider 抽象基类."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class OCRResult:
    """统一 OCR 结果."""

    text: str
    blocks: list[dict[str, Any]]  # 带 bbox 的原始块
    confidence: float = 0.0
    raw: Any = None


class OCRProvider(ABC):
    """从图片里提取文字."""

    provider_name: str = "abstract"

    @abstractmethod
    async def recognize(
        self,
        image: bytes,
        *,
        mime: str = "image/png",
        language: str = "auto",
        **kwargs: Any,
    ) -> OCRResult: ...

    @abstractmethod
    async def recognize_url(
        self,
        url: str,
        *,
        language: str = "auto",
        **kwargs: Any,
    ) -> OCRResult: ...
