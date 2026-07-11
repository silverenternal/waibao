"""Vision Mock Provider — 不真去解析图像,返回与协议相符的占位响应."""
from __future__ import annotations

from typing import Any

from .base import ImageInput, VisionMessage, VisionProvider, VisionResponse


class MockVisionProvider(VisionProvider):
    """纯本地 mock,不发起任何网络请求."""

    provider_name = "mock"

    @property
    def supported_models(self) -> list[str]:
        return ["mock-vision"]

    @property
    def pricing(self) -> dict[str, tuple[float, float]]:
        return {"mock-vision": (0.0, 0.0)}

    async def chat_with_images(
        self,
        messages: list[VisionMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> VisionResponse:
        last_text = messages[-1].text if messages else ""
        n_images = sum(len(m.images) for m in messages)
        content = f"[mock-vision] echo: {last_text} (images={n_images})"
        return VisionResponse(
            content=content,
            model="mock-vision",
            usage_tokens=len(last_text) // 2,
        )

    async def ocr(
        self,
        image: ImageInput,
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        src = image.url or ("inline-bytes" if image.data else "unknown")
        return f"[mock-vision-ocr] src={src}"