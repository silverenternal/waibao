"""天眼查 Provider (OpenAPI).

官方 API 文档:https://open.tianyancha.com/.
鉴权方式:Authorization: <api_key>.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from ..base import with_resilience
from ..exceptions import InvalidRequestError, ProviderError
from .base import CompanyInfo, CompanyLookupProvider


class TianyanchaProvider(CompanyLookupProvider):
    """天眼查企业信息查询."""

    provider_name = "tianyancha"
    BASE_URL = "https://open.tianyancha.com/services/open/ic/baseinfo/2.0"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        rate_per_sec: float = 5.0,
        burst: int = 10,
    ) -> None:
        self.api_key = api_key or os.getenv("TIANYANCHA_API_KEY", "")
        if not self.api_key:
            raise InvalidRequestError(
                "TIANYANCHA_API_KEY is required", provider="tianyancha"
            )
        self.base_url = base_url or os.getenv(
            "TIANYANCHA_BASE_URL", self.BASE_URL
        )
        self._client = httpx.AsyncClient(
            timeout=20.0,
            headers={"Authorization": self.api_key},
        )
        self._rate_per_sec = rate_per_sec
        self._burst = burst

    @with_resilience(provider="tianyancha", method="search", rate_per_sec=5.0, burst=10)
    async def search(self, keyword: str, **kwargs: Any) -> list[CompanyInfo]:
        params = {"keyword": keyword}
        params.update(kwargs)
        try:
            r = await self._client.get(self.base_url, params=params)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as exc:
            raise _map_http(exc, "tianyancha") from exc
        except Exception as exc:
            raise ProviderError(str(exc), provider="tianyancha") from exc
        items = (data.get("result") or {}).get("items", []) or []
        return [self._to_companyinfo(it) for it in items]

    @with_resilience(provider="tianyancha", method="get_detail", rate_per_sec=5.0, burst=10)
    async def get_detail(self, company_id: str, **kwargs: Any) -> CompanyInfo:
        params = {"id": company_id}
        params.update(kwargs)
        try:
            r = await self._client.get(self.base_url, params=params)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as exc:
            raise _map_http(exc, "tianyancha") from exc
        except Exception as exc:
            raise ProviderError(str(exc), provider="tianyancha") from exc
        return self._to_companyinfo(data.get("result") or {})

    def _to_companyinfo(self, raw: dict[str, Any]) -> CompanyInfo:
        return CompanyInfo(
            name=raw.get("name", ""),
            legal_representative=raw.get("legalPersonName"),
            registered_capital=raw.get("regCapital"),
            established_date=raw.get("estiblishTime"),
            status=raw.get("regStatus"),
            industry=raw.get("industry"),
            business_scope=raw.get("businessScope"),
            address=raw.get("regLocation"),
            unified_social_credit_code=raw.get("creditCode"),
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
