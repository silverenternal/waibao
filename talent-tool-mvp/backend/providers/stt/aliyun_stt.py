"""阿里云 ASR (一句话识别 / 录音文件识别).

短音频走一句话识别 (Recognition);长音频走文件识别 (FileTrans) 异步轮询。
本实现默认短音频一句话识别。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any

import httpx

from ..base import with_resilience
from ..exceptions import InvalidRequestError, ProviderError
from .base import STTProvider, STTResult


class AliyunSTTProvider(STTProvider):
    """阿里云一句话识别 (nlsasr)."""

    provider_name = "aliyun"
    HOST = "https://nls-meta.cn-shanghai.aliyuncs.com/"
    ACTION = "RecognizeShortAudio"
    VERSION = "2021-08-20"

    def __init__(
        self,
        access_key_id: str | None = None,
        access_key_secret: str | None = None,
        *,
        app_key: str | None = None,
        rate_per_sec: float = 20.0,
        burst: int = 40,
    ) -> None:
        self.ak = access_key_id or os.getenv("ALIYUN_ACCESS_KEY_ID", "")
        self.sk = access_key_secret or os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
        self.app_key = app_key or os.getenv("ALIYUN_ASR_APP_KEY", "")
        if not self.ak or not self.sk or not self.app_key:
            raise InvalidRequestError(
                "ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET / ALIYUN_ASR_APP_KEY are required",
                provider="aliyun_stt",
            )
        self._client = httpx.AsyncClient(timeout=30.0)
        self._rate_per_sec = rate_per_sec
        self._burst = burst

    def _sign(self, params: dict[str, str]) -> str:
        sorted_keys = sorted(params.keys())
        canonicalized = "&".join(
            f"{_percent_encode(k)}={_percent_encode(params[k])}" for k in sorted_keys
        )
        string_to_sign = "POST&%2F&" + _percent_encode(canonicalized)
        h = hmac.new(
            (self.sk + "&").encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1,
        )
        return base64.b64encode(h.digest()).decode("ascii")

    @with_resilience(provider="aliyun_stt", method="transcribe", rate_per_sec=20.0, burst=40)
    async def transcribe(
        self,
        audio: bytes,
        *,
        mime: str = "audio/mpeg",
        language: str = "auto",
        **kwargs: Any,
    ) -> STTResult:
        body = json.dumps(
            {
                "app_key": self.app_key,
                "format": mime.split("/")[-1] if "/" in mime else "mp3",
                "sample_rate": 16000,
                "enable_punctuation_prediction": True,
                "enable_inverse_text_normalization": True,
                "audio": base64.b64encode(audio).decode("ascii"),
            },
            ensure_ascii=False,
        )
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
        params["Signature"] = self._sign(params)
        try:
            r = await self._client.post(
                self.HOST,
                params=params,
                content=body,
                headers={"Content-Type": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as exc:
            raise _map_http(exc, "aliyun_stt") from exc
        except Exception as exc:
            raise ProviderError(str(exc), provider="aliyun_stt") from exc

        if data.get("status") != 20000000:
            raise ProviderError(
                f"aliyun_stt error: {data}", provider="aliyun_stt"
            )
        result = data.get("result", "") or ""
        return STTResult(text=result, language=language if language != "auto" else None, raw=data)

    async def transcribe_url(
        self, url: str, *, language: str = "auto", **kwargs: Any
    ) -> STTResult:
        async with httpx.AsyncClient(timeout=60.0) as c:
            r = await c.get(url)
            r.raise_for_status()
            data = r.content
        return await self.transcribe(data, language=language, **kwargs)


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
