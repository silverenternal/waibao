"""阿里云 OCR Provider (读光 OCR,RecognizeAdvanced).

使用 AccessKey 签名 (RPC API 风格)。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
import uuid
from typing import Any

import httpx

from ..base import with_resilience
from ..exceptions import InvalidRequestError, ProviderError
from .base import OCRProvider, OCRResult


class AliyunOCRProvider(OCRProvider):
    """阿里云读光 OCR."""

    provider_name = "aliyun"
    HOST = "https://ocr-api.cn-hangzhou.aliyuncs.com/"
    ACTION = "RecognizeAdvanced"
    VERSION = "2021-07-07"

    def __init__(
        self,
        access_key_id: str | None = None,
        access_key_secret: str | None = None,
        *,
        rate_per_sec: float = 20.0,
        burst: int = 40,
    ) -> None:
        self.ak = access_key_id or os.getenv("ALIYUN_ACCESS_KEY_ID", "")
        self.sk = access_key_secret or os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
        if not self.ak or not self.sk:
            raise InvalidRequestError(
                "ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET are required",
                provider="aliyun_ocr",
            )
        self._client = httpx.AsyncClient(timeout=30.0)
        self._rate_per_sec = rate_per_sec
        self._burst = burst

    def _sign(
        self, params: dict[str, str], body: str
    ) -> str:
        """RPC 风格 HMAC-SHA1 签名 (阿里云 v3 简化版)."""
        sorted_keys = sorted(params.keys())
        canonicalized = "&".join(
            f"{_percent_encode(k)}={_percent_encode(params[k])}" for k in sorted_keys
        )
        string_to_sign = (
            "POST"
            + "&"
            + _percent_encode("/")
            + "&"
            + _percent_encode(canonicalized)
        )
        h = hmac.new(
            (self.sk + "&").encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1,
        )
        return base64.b64encode(h.digest()).decode("ascii")

    @with_resilience(provider="aliyun_ocr", method="recognize", rate_per_sec=20.0, burst=40)
    async def recognize(
        self,
        image: bytes,
        *,
        mime: str = "image/png",
        language: str = "auto",
        **kwargs: Any,
    ) -> OCRResult:
        body_dict: dict[str, Any] = {"img": base64.b64encode(image).decode("ascii")}
        if language != "auto":
            body_dict["language"] = language
        body_dict.update(kwargs)
        import json

        body = json.dumps(body_dict, ensure_ascii=False, separators=(",", ":"))

        params: dict[str, str] = {
            "Format": "JSON",
            "Version": self.VERSION,
            "AccessKeyId": self.ak,
            "SignatureMethod": "HMAC-SHA1",
            "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "SignatureVersion": "1.0",
            "SignatureNonce": str(uuid.uuid4()),
            "Action": self.ACTION,
        }
        params["Signature"] = self._sign(params, body)
        try:
            r = await self._client.post(
                self.HOST, params=params, content=body, headers={"Content-Type": "application/json"}
            )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as exc:
            raise _map_http(exc, "aliyun_ocr") from exc
        except Exception as exc:
            raise ProviderError(str(exc), provider="aliyun_ocr") from exc

        if "Code" in data and data.get("Code") != "200":
            raise ProviderError(
                f"aliyun_ocr api error: {data}", provider="aliyun_ocr"
            )
        content = data.get("Data", "") or ""
        # Data 可能是 base64(JSON) 或直接的 JSON 字符串
        import base64 as _b64

        try:
            decoded = _b64.b64decode(content).decode("utf-8")
            sub = json.loads(decoded)
        except Exception:
            sub = {}
        blocks = sub.get("prunedResult", []) or sub.get("content", [])
        text = "\n".join(
            (b.get("text") if isinstance(b, dict) else str(b)) for b in blocks
        )
        if not text and isinstance(sub.get("content"), str):
            text = sub["content"]
        return OCRResult(text=text, blocks=blocks, raw=data)

    async def recognize_url(
        self, url: str, *, language: str = "auto", **kwargs: Any
    ) -> OCRResult:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.get(url)
            r.raise_for_status()
            data = r.content
        return await self.recognize(data, language=language, **kwargs)


def _percent_encode(s: str) -> str:
    from urllib.parse import quote

    return quote(s, safe="~")


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
