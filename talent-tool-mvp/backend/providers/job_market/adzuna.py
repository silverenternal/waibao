"""Adzuna Job Search API 适配器 (T607).

Adzuna 是免费的全球职位聚合 API:
    - 文档: https://developer.adzuna.com/docs/search
    - 鉴权: `app_id` + `app_key` (URL query)
    - 免费层: 250 calls/month
    - 接口: GET /v1/api/jobs/{country}/search
    - 覆盖: GB / US / AU / DE / FR / AT / BE / CA / CH / ES / IN / IT / MX / NL / NZ / PL / SG / ZA

降级策略: 任何 ProviderError / 网络错误 → 自动 fallback 到 MockJobMarketProvider
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..base import RetryPolicy, with_resilience
from ..exceptions import (
    AuthError,
    ProviderError,
    QuotaExceededError,
    UpstreamUnavailableError,
)
from .base import JobMarketProvider
from .mock import MockJobMarketProvider
from .types import JobPosting, SalaryPoint, SkillDemand

logger = logging.getLogger(__name__)

_ADZUNA_BASE = os.getenv("JOB_MARKET_ADZUNA_BASE", "https://api.adzuna.com/v1/api/jobs")
_ADZUNA_APP_ID = os.getenv("JOB_MARKET_ADZUNA_APP_ID", "")
_ADZUNA_APP_KEY = os.getenv("JOB_MARKET_ADZUNA_APP_KEY", "")
_ADZUNA_COUNTRY = os.getenv("JOB_MARKET_ADZUNA_COUNTRY", "gb")
_ADZUNA_TIMEOUT = float(os.getenv("JOB_MARKET_ADZUNA_TIMEOUT", "8.0"))


class AdzunaProvider(JobMarketProvider):
    """Adzuna 适配器. 失败自动 fallback 到 MockJobMarketProvider."""

    provider_name = "adzuna"

    def __init__(self, *, fallback: JobMarketProvider | None = None) -> None:
        self._fallback = fallback or MockJobMarketProvider()
        self._client: httpx.AsyncClient | None = None

    def _has_credentials(self) -> bool:
        return bool(_ADZUNA_APP_ID and _ADZUNA_APP_KEY)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=_ADZUNA_TIMEOUT,
                headers={"User-Agent": "waibao/3.0"},
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # search_jobs
    # ------------------------------------------------------------------
    @with_resilience(
        provider="job_market_adzuna",
        method="search_jobs",
        retry=RetryPolicy(max_retries=2, base_delay=0.8, max_delay=4.0),
        rate_per_sec=2.0,
        burst=5,
    )
    async def search_jobs(
        self,
        keyword: str,
        *,
        city: str | None = None,
        salary_range: tuple[float, float] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[JobPosting]:
        if not keyword:
            return []
        if not self._has_credentials():
            return await self._fallback.search_jobs(
                keyword, city=city, salary_range=salary_range,
                page=page, page_size=page_size,
            )
        client = await self._get_client()
        params: dict[str, Any] = {
            "app_id": _ADZUNA_APP_ID,
            "app_key": _ADZUNA_APP_KEY,
            "results_per_page": page_size,
            "what": keyword,
            "page": page,
            "content-type": "application/json",
        }
        if city:
            params["where"] = city
        try:
            resp = await client.get(f"/{_ADZUNA_COUNTRY}/search", params=params)
        except httpx.HTTPError as exc:
            logger.warning("adzuna.search network error: %s → fallback", exc)
            return await self._fallback.search_jobs(
                keyword, city=city, salary_range=salary_range,
                page=page, page_size=page_size,
            )
        return self._parse(resp, salary_range)

    def _parse(
        self,
        resp: httpx.Response,
        salary_range: tuple[float, float] | None,
    ) -> list[JobPosting]:
        if resp.status_code in (401, 403):
            raise AuthError("adzuna auth failed", provider="adzuna")
        if resp.status_code == 402:
            raise QuotaExceededError("adzuna quota exhausted", provider="adzuna")
        if resp.status_code >= 500:
            raise UpstreamUnavailableError(
                f"adzuna 5xx {resp.status_code}", provider="adzuna",
            )
        try:
            payload = resp.json()
        except Exception as exc:
            raise UpstreamUnavailableError(
                f"adzuna bad json: {exc}", provider="adzuna",
            ) from exc
        results = payload.get("results") or []
        out: list[JobPosting] = []
        for raw in results:
            out.append(self._to_posting(raw))
        if salary_range is not None:
            lo, hi = salary_range
            out = [
                j for j in out
                if j.salary_min_k is not None
                and j.salary_max_k is not None
                and j.salary_min_k >= lo
                and j.salary_max_k <= hi
            ]
        return out

    def _to_posting(self, raw: dict[str, Any]) -> JobPosting:
        loc = raw.get("location") or {}
        area = loc.get("area") if isinstance(loc, dict) else []
        city = area[0] if area else None
        sal_min = raw.get("salary_min")
        sal_max = raw.get("salary_max")
        return JobPosting(
            source="adzuna",
            external_id=str(raw.get("id") or ""),
            title=str(raw.get("title") or ""),
            company=str(raw.get("company") or {}).get("display_name", "")
            if isinstance(raw.get("company"), dict)
            else str(raw.get("company") or ""),
            city=city,
            salary_min_k=sal_min,
            salary_max_k=sal_max,
            salary_currency="GBP" if _ADZUNA_COUNTRY == "gb" else "USD",
            experience_years=None,
            education=None,
            skills=[],
            url=raw.get("redirect_url"),
            posted_at=raw.get("created"),
            description_snippet=(raw.get("description") or "")[:280] or None,
            raw=raw,
        )

    # ------------------------------------------------------------------
    # get_salary_trend (Adzuna 提供 /history 接口)
    # ------------------------------------------------------------------
    @with_resilience(
        provider="job_market_adzuna",
        method="get_salary_trend",
        retry=RetryPolicy(max_retries=2, base_delay=0.8, max_delay=4.0),
        rate_per_sec=2.0,
        burst=5,
    )
    async def get_salary_trend(
        self,
        role: str,
        city: str,
        *,
        months: int = 12,
    ) -> list[SalaryPoint]:
        if not self._has_credentials():
            return await self._fallback.get_salary_trend(role, city, months=months)
        client = await self._get_client()
        params = {
            "app_id": _ADZUNA_APP_ID,
            "app_key": _ADZUNA_APP_KEY,
            "what": role,
            "where": city,
            "months": min(months, 12),
            "content-type": "application/json",
        }
        try:
            resp = await client.get(f"/{_ADZUNA_COUNTRY}/history", params=params)
        except httpx.HTTPError as exc:
            logger.warning("adzuna.history network error: %s → fallback", exc)
            return await self._fallback.get_salary_trend(role, city, months=months)
        if resp.status_code >= 400:
            return await self._fallback.get_salary_trend(role, city, months=months)
        try:
            payload = resp.json()
            month_data = payload.get("month") or {}
        except Exception:
            return await self._fallback.get_salary_trend(role, city, months=months)
        out: list[SalaryPoint] = []
        for period, median in sorted(month_data.items()):
            try:
                median_f = float(median)
            except (TypeError, ValueError):
                continue
            out.append(SalaryPoint(
                period=period,
                median_k=median_f,
                p25_k=None,
                p75_k=None,
                sample_size=None,
                currency="GBP" if _ADZUNA_COUNTRY == "gb" else "USD",
            ))
        return out or await self._fallback.get_salary_trend(role, city, months=months)

    # ------------------------------------------------------------------
    # get_hot_skills (Adzuna 不提供 → fallback)
    # ------------------------------------------------------------------
    async def get_hot_skills(
        self,
        role: str | None = None,
        *,
        limit: int = 20,
    ) -> list[SkillDemand]:
        return await self._fallback.get_hot_skills(role, limit=limit)


__all__ = ["AdzunaProvider"]