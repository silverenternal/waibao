"""启信宝 Provider (OpenAPI).

鉴权方式:Authorization: <appkey> + timestamp + signature (md5(appSecret+timestamp)).
"""
from __future__ import annotations

import hashlib
import os
import time
from typing import Any

import httpx

from ..base import with_resilience
from ..exceptions import InvalidRequestError, ProviderError
from .base import CompanyInfo, CompanyLookupProvider


class QichachaProvider(CompanyLookupProvider):
    """启信宝企业信息查询."""

    provider_name = "qichacha"
    BASE_URL = "https://api.qichacha.com/ECIV4/GetBasicDetailsByName"

    def __init__(
        self,
        app_key: str | None = None,
        app_secret: str | None = None,
        base_url: str | None = None,
        *,
        rate_per_sec: float = 5.0,
        burst: int = 10,
    ) -> None:
        self.app_key = app_key or os.getenv("QICHACHA_APP_KEY", "")
        self.app_secret = app_secret or os.getenv("QICHACHA_APP_SECRET", "")
        if not self.app_key or not self.app_secret:
            raise InvalidRequestError(
                "QICHACHA_APP_KEY / QICHACHA_APP_SECRET are required",
                provider="qichacha",
            )
        self.base_url = base_url or os.getenv(
            "QICHACHA_BASE_URL", self.BASE_URL
        )
        self._client = httpx.AsyncClient(timeout=20.0)
        self._rate_per_sec = rate_per_sec
        self._burst = burst

    def _sign(self) -> str:
        timestamp = str(int(time.time()))
        return timestamp, hashlib.md5(
            (self.app_key + timestamp).encode("utf-8")
        ).hexdigest() + "," + timestamp

    @with_resilience(provider="qichacha", method="search", rate_per_sec=5.0, burst=10)
    async def search(self, keyword: str, **kwargs: Any) -> list[CompanyInfo]:
        _, sign = self._sign()
        params = {
            "key": self.app_key,
            "keyword": keyword,
            "sign": sign,
        }
        params.update(kwargs)
        try:
            r = await self._client.get(self.base_url, params=params)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as exc:
            raise _map_http(exc, "qichacha") from exc
        except Exception as exc:
            raise ProviderError(str(exc), provider="qichacha") from exc
        items = (data.get("Result") or {}).get("items", []) or []
        return [self._to_companyinfo(it) for it in items]

    @with_resilience(provider="qichacha", method="get_detail", rate_per_sec=5.0, burst=10)
    async def get_detail(self, company_id: str, **kwargs: Any) -> CompanyInfo:
        # 启信宝详情接口路径不同,这里给个占位实现
        params = {
            "key": self.app_key,
            "id": company_id,
            "sign": self._sign()[1],
        }
        params.update(kwargs)
        r = await self._client.get(self.base_url, params=params)
        r.raise_for_status()
        data = r.json()
        return self._to_companyinfo(data.get("Result") or {})

    def _to_companyinfo(self, raw: dict[str, Any]) -> CompanyInfo:
        return CompanyInfo(
            name=raw.get("Name", ""),
            legal_representative=raw.get("LegalPerson"),
            registered_capital=raw.get("RegistCapi"),
            established_date=raw.get("StartDate"),
            status=raw.get("Status"),
            industry=raw.get("Industry"),
            business_scope=raw.get("Scope"),
            address=raw.get("Address"),
            unified_social_credit_code=raw.get("CreditCode"),
            raw=raw,
        )


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
