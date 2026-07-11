"""Qwen-VL 多模态 Provider.

DashScope 提供 qwen-vl-plus / qwen-vl-max,通过 HTTP API 调用。
"""
from __future__ import annotations

import base64
import os
from typing import Any

import httpx

from ..base import with_resilience
from ..exceptions import InvalidRequestError, ProviderError
from .base import ImageInput, VisionMessage, VisionProvider, VisionResponse


class QwenVLProvider(VisionProvider):
    """通义千问 Qwen-VL 系列."""

    provider_name = "qwen_vl"

    PRICING: dict[str, tuple[float, float]] = {
        "qwen-vl-plus": (0.008, 0.008),  # 元/千 token,占位
        "qwen-vl-max": (0.02, 0.02),
    }

    ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        default_model: str = "qwen-vl-plus",
        rate_per_sec: float = 10.0,
        burst: int = 20,
    ) -> None:
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "") or os.getenv(
            "TONGYI_API_KEY", ""
        )
        if not self.api_key:
            raise InvalidRequestError(
                "DASHSCOPE_API_KEY is required", provider="qwen_vl"
            )
        self.base_url = base_url or os.getenv("DASHSCOPE_BASE_URL", self.ENDPOINT)
        self.default_model = default_model
        self._client = httpx.AsyncClient(timeout=60.0)
        self._rate_per_sec = rate_per_sec
        self._burst = burst

    @property
    def supported_models(self) -> list[str]:
        return list(self.PRICING.keys())

    @property
    def pricing(self) -> dict[str, tuple[float, float]]:
        return dict(self.PRICING)

    def _content_for(self, img: ImageInput) -> dict[str, Any]:
        if img.is_remote():
            return {"image": img.url}
        if img.data is not None:
            b64 = base64.b64encode(img.data).decode("ascii")
            mime = img.mime or "image/png"
            return {"image": f"data:{mime};base64,{b64}"}
        raise InvalidRequestError("ImageInput 缺少 url/data", provider="qwen_vl")

    def _build_messages(
        self, messages: list[VisionMessage]
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            content: list[dict[str, Any]] = []
            for img in m.images:
                content.append(self._content_for(img))
            if m.text:
                content.append({"text": m.text})
            out.append({"role": m.role, "content": content})
        return out

    @with_resilience(provider="qwen_vl", method="chat_with_images", rate_per_sec=10.0, burst=20)
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
        payload: dict[str, Any] = {
            "model": model,
            "input": {"messages": self._build_messages(messages)},
            "parameters": {"temperature": temperature, "max_tokens": max_tokens},
        }
        payload.update(kwargs)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            r = await self._client.post(self.base_url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as exc:
            raise _map_http(exc, "qwen_vl") from exc
        except Exception as exc:
            raise ProviderError(str(exc), provider="qwen_vl") from exc

        try:
            content = (
                data["output"]["choices"][0]["message"]["content"]
                if isinstance(data["output"]["choices"][0]["message"]["content"], str)
                else data["output"]["choices"][0]["message"]["content"][0]["text"]
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"qwen_vl 响应结构异常: {data}", provider="qwen_vl") from exc
        usage = data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get(
            "output_tokens", 0
        )
        return VisionResponse(content=content, model=model, usage_tokens=usage, raw=data)

    async def ocr(self, image: ImageInput, *, model: str | None = None, **kwargs: Any) -> str:
        messages = [
            VisionMessage(
                role="user",
                text="请把图片中所有文字按原文顺序完整转录出来,不要翻译,不要总结。",
                images=[image],
            )
        ]
        resp = await self.chat_with_images(messages, model=model, **kwargs)
        return resp.content


def _map_http(exc: httpx.HTTPStatusError, provider: str) -> ProviderError:
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
