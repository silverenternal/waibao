"""百度 OCR Provider.

先获取 access_token (client_credentials),再调通用文字识别 basicAccurate / general.
"""
from __future__ import annotations

import base64
import os
import time
from typing import Any

import httpx

from ..base import with_resilience
from ..exceptions import InvalidRequestError, ProviderError
from .base import OCRProvider, OCRResult


class BaiduOCRProvider(OCRProvider):
    """百度 OCR (默认 basicAccurate)."""

    provider_name = "baidu"
    TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
    OCR_URL = (
        "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic"
    )

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        *,
        rate_per_sec: float = 10.0,
        burst: int = 20,
    ) -> None:
        self.api_key = api_key or os.getenv("BAIDU_OCR_API_KEY", "")
        self.secret_key = secret_key or os.getenv("BAIDU_OCR_SECRET_KEY", "")
        if not self.api_key or not self.secret_key:
            raise InvalidRequestError(
                "BAIDU_OCR_API_KEY / BAIDU_OCR_SECRET_KEY are required",
                provider="baidu_ocr",
            )
        self._client = httpx.AsyncClient(timeout=30.0)
        self._token: str | None = None
        self._token_expire_at: float = 0.0
        self._rate_per_sec = rate_per_sec
        self._burst = burst

    async def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_expire_at - 60:
            return self._token
        params = {
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "client_secret": self.secret_key,
        }
        r = await self._client.get(self.TOKEN_URL, params=params)
        r.raise_for_status()
        data = r.json()
        if "access_token" not in data:
            raise ProviderError(
                f"baidu_ocr token error: {data}", provider="baidu_ocr"
            )
        self._token = data["access_token"]
        self._token_expire_at = time.time() + int(data.get("expires_in", 2592000))
        return self._token

    @with_resilience(provider="baidu_ocr", method="recognize", rate_per_sec=10.0, burst=20)
    async def recognize(
        self,
        image: bytes,
        *,
        mime: str = "image/png",
        language: str = "auto",
        **kwargs: Any,
    ) -> OCRResult:
        token = await self._ensure_token()
        params = {"access_token": token}
        data_form: dict[str, Any] = {
            "image": base64.b64encode(image).decode("ascii"),
        }
        if language != "auto":
            data_form["language_type"] = language
        data_form.update(kwargs)
        try:
            r = await self._client.post(self.OCR_URL, params=params, data=data_form)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as exc:
            raise _map_http(exc, "baidu_ocr") from exc
        except Exception as exc:
            raise ProviderError(str(exc), provider="baidu_ocr") from exc

        if "error_code" in data:
            raise ProviderError(
                f"baidu_ocr api error: {data}", provider="baidu_ocr"
            )
        words = data.get("words_result", []) or []
        text = "\n".join(w.get("words", "") for w in words)
        return OCRResult(
            text=text,
            blocks=words,
            confidence=sum(
                float(w.get("probability", {}).get("average", 0.0)) for w in words
            )
            / max(len(words), 1),
            raw=data,
        )

    async def recognize_url(
        self, url: str, *, language: str = "auto", **kwargs: Any
    ) -> OCRResult:
        token = await self._ensure_token()
        params = {"access_token": token}
        data_form: dict[str, Any] = {"url": url}
        if language != "auto":
            data_form["language_type"] = language
        data_form.update(kwargs)
        r = await self._client.post(self.OCR_URL, params=params, data=data_form)
        r.raise_for_status()
        data = r.json()
        words = data.get("words_result", []) or []
        text = "\n".join(w.get("words", "") for w in words)
        return OCRResult(text=text, blocks=words, raw=data)


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
