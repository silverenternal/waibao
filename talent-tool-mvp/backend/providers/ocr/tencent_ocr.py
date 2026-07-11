"""腾讯云 OCR Provider (通用印刷体 / 通用手写体).

通过 SecretId + SecretKey 计算 TC3-HMAC-SHA256 签名,调用 GeneralBasicOCR 接口。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from ..base import with_resilience
from ..exceptions import InvalidRequestError, ProviderError
from .base import OCRProvider, OCRResult


class TencentOCRProvider(OCRProvider):
    """腾讯云 OCR (默认 GeneralBasicOCR)."""

    provider_name = "tencent"
    HOST = "ocr.tencentcloudapi.com"
    SERVICE = "ocr"
    ACTION = "GeneralBasicOCR"
    VERSION = "2018-11-19"

    def __init__(
        self,
        secret_id: str | None = None,
        secret_key: str | None = None,
        *,
        region: str = "ap-guangzhou",
        rate_per_sec: float = 20.0,
        burst: int = 40,
    ) -> None:
        self.secret_id = secret_id or os.getenv("TENCENT_SECRET_ID", "")
        self.secret_key = secret_key or os.getenv("TENCENT_SECRET_KEY", "")
        if not self.secret_id or not self.secret_key:
            raise InvalidRequestError(
                "TENCENT_SECRET_ID / TENCENT_SECRET_KEY are required",
                provider="tencent_ocr",
            )
        self.region = region
        self._client = httpx.AsyncClient(timeout=30.0)
        self._rate_per_sec = rate_per_sec
        self._burst = burst

    def _sign(self, payload: str) -> dict[str, str]:
        """TC3-HMAC-SHA256 签名."""
        timestamp = int(time.time())
        date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
        canonical_uri = "/"
        canonical_query = ""
        canonical_headers = (
            f"content-type:application/json; charset=utf-8\n"
            f"host:{self.HOST}\n"
            f"x-tc-action:{self.ACTION.lower()}\n"
        )
        signed_headers = "content-type;host;x-tc-action"
        hashed_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        canonical_request = (
            "POST\n"
            f"{canonical_uri}\n"
            f"{canonical_query}\n"
            f"{canonical_headers}\n"
            f"{signed_headers}\n"
            f"{hashed_payload}"
        )
        credential_scope = f"{date}/{self.SERVICE}/tc3_request"
        string_to_sign = (
            "TC3-HMAC-SHA256\n"
            f"{timestamp}\n"
            f"{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )
        secret_date = hmac.new(
            f"TC3{self.secret_key}".encode("utf-8"), date.encode("utf-8"), hashlib.sha256
        ).digest()
        secret_service = hmac.new(
            secret_date, self.SERVICE.encode("utf-8"), hashlib.sha256
        ).digest()
        secret_signing = hmac.new(
            secret_service, "tc3_request".encode("utf-8"), hashlib.sha256
        ).digest()
        signature = hmac.new(
            secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return {
            "Authorization": (
                f"TC3-HMAC-SHA256 Credential={self.secret_id}/{credential_scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}"
            ),
            "X-TC-Action": self.ACTION,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": self.VERSION,
            "X-TC-Region": self.region,
            "Content-Type": "application/json; charset=utf-8",
        }

    @with_resilience(provider="tencent_ocr", method="recognize", rate_per_sec=20.0, burst=40)
    async def recognize(
        self,
        image: bytes,
        *,
        mime: str = "image/png",
        language: str = "auto",
        **kwargs: Any,
    ) -> OCRResult:
        payload_dict: dict[str, Any] = {
            "ImageBase64": base64.b64encode(image).decode("ascii"),
        }
        if language != "auto":
            payload_dict["Language"] = language
        payload_dict.update(kwargs)
        payload = json.dumps(payload_dict, ensure_ascii=False)
        headers = self._sign(payload)
        try:
            r = await self._client.post(
                f"https://{self.HOST}", content=payload, headers=headers
            )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as exc:
            raise _map_http(exc, "tencent_ocr") from exc
        except Exception as exc:
            raise ProviderError(str(exc), provider="tencent_ocr") from exc

        if "Response" not in data or "Error" in data.get("Response", {}):
            raise ProviderError(
                f"tencent_ocr error: {data}", provider="tencent_ocr"
            )
        items = data["Response"].get("TextDetections", []) or []
        text = "\n".join(it.get("DetectedText", "") for it in items)
        return OCRResult(
            text=text,
            blocks=items,
            confidence=sum(it.get("Confidence", 0) for it in items) / max(len(items), 1),
            raw=data,
        )

    async def recognize_url(
        self, url: str, *, language: str = "auto", **kwargs: Any
    ) -> OCRResult:
        # 通过 ImageUrl 字段重发,需在 recognize 基础上换 payload;此处简化:先把 URL 内容拉下来
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.get(url)
            r.raise_for_status()
            data = r.content
        return await self.recognize(data, language=language, **kwargs)


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
