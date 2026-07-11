"""Vision (多模态) Provider 抽象基类."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ImageInput:
    """图片输入.

    支持两种来源:
        - url: 远程 URL (供应商去拉取)
        - data: base64 编码的图片数据 (mime + bytes)
    """

    url: str | None = None
    mime: str | None = None
    data: bytes | None = None

    def is_remote(self) -> bool:
        return self.url is not None


@dataclass(slots=True)
class VisionMessage:
    """Vision 专用的多模态消息."""

    role: str
    text: str
    images: list[ImageInput] = field(default_factory=list)


@dataclass(slots=True)
class VisionResponse:
    """统一的 vision 响应."""

    content: str
    model: str
    usage_tokens: int = 0
    raw: Any = None


class VisionProvider(ABC):
    """多模态 (图像理解) provider."""

    provider_name: str = "abstract"

    @property
    @abstractmethod
    def supported_models(self) -> list[str]: ...

    @property
    @abstractmethod
    def pricing(self) -> dict[str, tuple[float, float]]: ...

    @abstractmethod
    async def chat_with_images(
        self,
        messages: list[VisionMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> VisionResponse: ...

    @abstractmethod
    async def ocr(
        self,
        image: ImageInput,
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        """从图片中提取文字 (OCR 复用)."""

    async def stream_chat_with_images(
        self,
        messages: list[VisionMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """默认实现:非流式响应,逐字符 yield."""
        resp = await self.chat_with_images(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        for ch in resp.content:
            yield ch
