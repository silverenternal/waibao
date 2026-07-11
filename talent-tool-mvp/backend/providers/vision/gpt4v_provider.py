"""GPT-4V / GPT-4o 多模态 provider.

复用 OpenAI chat completions 接口,通过 content 数组传入 image_url。
"""
from __future__ import annotations

import base64
import os
from typing import Any

from openai import AsyncOpenAI

from ..base import with_resilience
from ..exceptions import InvalidRequestError, ProviderError
from .base import ImageInput, VisionMessage, VisionProvider, VisionResponse


class GPT4VProvider(VisionProvider):
    """GPT-4o / GPT-4V 多模态."""

    provider_name = "gpt4v"

    PRICING: dict[str, tuple[float, float]] = {
        "gpt-4o": (2.5, 10.0),
        "gpt-4o-mini": (0.15, 0.6),
    }

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        default_model: str = "gpt-4o-mini",
        rate_per_sec: float = 10.0,
        burst: int = 20,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        if not self.api_key:
            raise InvalidRequestError("OPENAI_API_KEY is required", provider="gpt4v")
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=base_url or os.getenv("OPENAI_BASE_URL"),
        )
        self.default_model = default_model
        self._rate_per_sec = rate_per_sec
        self._burst = burst

    @property
    def supported_models(self) -> list[str]:
        return list(self.PRICING.keys())

    @property
    def pricing(self) -> dict[str, tuple[float, float]]:
        return dict(self.PRICING)

    def _serialize_image(self, img: ImageInput) -> dict[str, Any]:
        if img.is_remote():
            return {"type": "image_url", "image_url": {"url": img.url}}
        if img.data is not None:
            b64 = base64.b64encode(img.data).decode("ascii")
            mime = img.mime or "image/png"
            return {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            }
        raise InvalidRequestError("ImageInput 必须有 url 或 data", provider="gpt4v")

    def _serialize_messages(self, messages: list[VisionMessage]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            content: list[dict[str, Any]] = []
            if m.text:
                content.append({"type": "text", "text": m.text})
            for img in m.images:
                content.append(self._serialize_image(img))
            out.append({"role": m.role, "content": content})
        return out

    @with_resilience(provider="gpt4v", method="chat_with_images", rate_per_sec=10.0, burst=20)
    async def chat_with_images(
        self,
        messages: list[VisionMessage],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> VisionResponse:
        model = model or self.default_model
        try:
            resp = await self.client.chat.completions.create(
                model=model,
                messages=self._serialize_messages(messages),
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
        except Exception as exc:
            raise _map(exc) from exc
        choice = resp.choices[0]
        usage = resp.usage.total_tokens if resp.usage else 0
        return VisionResponse(
            content=choice.message.content or "",
            model=resp.model,
            usage_tokens=usage,
            raw=resp,
        )

    async def ocr(self, image: ImageInput, *, model: str | None = None, **kwargs: Any) -> str:
        """GPT-4V OCR:让模型把图片里的文字完整转录."""
        messages = [
            VisionMessage(
                role="user",
                text="请把图片中所有文字按原文顺序完整转录出来,不要翻译,不要总结。",
                images=[image],
            )
        ]
        resp = await self.chat_with_images(messages, model=model, **kwargs)
        return resp.content


def _map(exc: Exception) -> ProviderError:
    from ..exceptions import (
        AuthError,
        InvalidRequestError,
        RateLimitError,
        UpstreamUnavailableError,
    )

    msg = str(exc)
    if "401" in msg:
        return AuthError(msg, provider="gpt4v")
    if "429" in msg:
        return RateLimitError(msg, provider="gpt4v")
    if "400" in msg:
        return InvalidRequestError(msg, provider="gpt4v")
    return UpstreamUnavailableError(msg, provider="gpt4v")
