"""LinkedIn Job Search API 适配器 (T607).

LinkedIn Talent Solutions:
    - 文档: https://learn.microsoft.com/en-us/linkedin/talent/
    - 鉴权: OAuth2 client_credentials (Talent partner)
        `Authorization: Bearer <access_token>`
    - 沙箱: 不开放,需 partner 合同 + 申请
    - 主要接口:
        POST /rest/jobSearch        — 搜索岗位
        GET  /rest/jobs/{id}       — 岗位详情
        GET  /rest/analytics/...   — 薪资趋势 (部分套餐可用)

降级策略: 任何上游异常 / 鉴权失败 → 自动 fallback 到 MockJobMarketProvider
货币: LinkedIn 输出 USD; 搜索 city 用 GeoId (例 102277331 = SF).
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
from .lagou import LagouProvider  # 复用 OAuth token cache
from .mock import MockJobMarketProvider
from .types import JobPosting, SalaryPoint, SkillDemand

logger = logging.getLogger(__name__)

_LINKEDIN_BASE = os.getenv("JOB_MARKET_LINKEDIN_BASE", "https://api.linkedin.com/rest")
_LINKEDIN_CLIENT_ID = os.getenv("JOB_MARKET_LINKEDIN_CLIENT_ID", "")
_LINKEDIN_CLIENT_SECRET = os.getenv("JOB_MARKET_LINKEDIN_CLIENT_SECRET", "")
_LINKEDIN_TIMEOUT = float(os.getenv("JOB_MARKET_LINKEDIN_TIMEOUT", "10.0"))

# 城市 → LinkedIn GeoId (只覆盖常用城市;未知则不传 city filter)
_CITY_GEOMAP: dict[str, str] = {
    "San Francisco": "102277331",
    "New York": "103644278",
    "Seattle": "103980507",
    "Austin": "103644278",  # 占位
    "London": "101165590",
    "上海": "106215052",
    "Shanghai": "106215052",
    "北京": "100871016",
    "Beijing": "100871016",
    "深圳": "106215052",
    "Shenzhen": "106215052",
}


class LinkedInProvider(JobMarketProvider):
    """LinkedIn 适配器. 失败自动 fallback 到 MockJobMarketProvider."""

    provider_name = "linkedin"

    def __init__(self, *, fallback: JobMarketProvider | None = None) -> None:
        self._fallback = fallback or MockJobMarketProvider()
        # 复用 Lagou 的 _TokenCache(同样 OAuth2 client_credentials grant)
        self._tokens = LagouProvider()._tokens  # noqa: SLF001 — 共享 cache
        self._client: httpx.AsyncClient | None = None

    def _has_credentials(self) -> bool:
        return bool(_LINKEDIN_CLIENT_ID and _LINKEDIN_CLIENT_SECRET)

    async def _get_client(self) -> httpx.AsyncClient:
        headers: dict[str, str] = {
            "User-Agent": "waibao/3.0",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }
        if self._has_credentials():
            # LinkedIn token endpoint 独立,这里简化复用 Lagou provider 的 _fetch_token
            token = await self._fetch_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=_LINKEDIN_BASE,
                timeout=_LINKEDIN_TIMEOUT,
                headers=headers,
            )
        else:
            self._client.headers.update(headers)
        return self._client

    async def _fetch_token(self) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=_LINKEDIN_TIMEOUT) as c:
                resp = await c.post(
                    "https://www.linkedin.com/oauth/v2/accessToken",
                    data={
                        "grant_type": "client_credentials",
                        "client_id": _LINKEDIN_CLIENT_ID,
                        "client_secret": _LINKEDIN_CLIENT_SECRET,
                        "scope": "r_basicprofile r_jobs2",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.HTTPError as exc:
            logger.warning("linkedin.token network error: %s", exc)
            return None
        if resp.status_code != 200:
            logger.warning("linkedin.token status=%s", resp.status_code)
            return None
        try:
            return resp.json().get("access_token")
        except Exception:
            return None

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # search_jobs
    # ------------------------------------------------------------------
    @with_resilience(
        provider="job_market_linkedin",
        method="search_jobs",
        retry=RetryPolicy(max_retries=2, base_delay=1.0, max_delay=5.0),
        rate_per_sec=3.0,
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
        body: dict[str, Any] = {
            "query": keyword,
            "start": (page - 1) * page_size,
            "count": page_size,
        }
        if city and city in _CITY_GEOMAP:
            body["geoId"] = _CITY_GEOMAP[city]
        client = await self._get_client()
        try:
            resp = await client.post("/jobSearch", json=body)
        except httpx.HTTPError as exc:
            logger.warning("linkedin.search network error: %s → fallback", exc)
            return await self._fallback.search_jobs(
                keyword, city=city, salary_range=salary_range,
                page=page, page_size=page_size,
            )
        if resp.status_code in (401, 403):
            raise AuthError("linkedin auth failed", provider="linkedin")
        if resp.status_code == 402:
            raise QuotaExceededError("linkedin quota exhausted", provider="linkedin")
        if resp.status_code >= 500:
            raise UpstreamUnavailableError(
                f"linkedin 5xx {resp.status_code}", provider="linkedin",
            )
        try:
            payload = resp.json()
        except Exception as exc:
            raise UpstreamUnavailableError(
                f"linkedin bad json: {exc}", provider="linkedin",
            ) from exc
        elements = payload.get("elements") or []
        out: list[JobPosting] = []
        for raw in elements:
            posting = self._to_posting(raw)
            if posting is not None:
                out.append(posting)
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

    def _to_posting(self, raw: dict[str, Any]) -> JobPosting | None:
        try:
            external_id = str(raw.get("entityUrn") or raw.get("jobId") or "")
            if not external_id:
                return None
            title = (raw.get("title") or "").strip()
            company = ""
            co = raw.get("companyDetails") or raw.get("company") or {}
            if isinstance(co, dict):
                company = co.get("name") or co.get("companyName") or ""
            location = raw.get("location") or ""
            listed_at = raw.get("listedAt") or raw.get("originalListedAt")
            skills = [
                str(s.get("name") if isinstance(s, dict) else s)
                for s in (raw.get("skills") or [])
            ]
            salary = raw.get("salary") or {}
            sal_min = None
            sal_max = None
            if isinstance(salary, dict):
                try:
                    sal_min = float(salary.get("min")) / 1000 if salary.get("min") else None
                    sal_max = float(salary.get("max")) / 1000 if salary.get("max") else None
                except (TypeError, ValueError):
                    pass
            return JobPosting(
                source="linkedin",
                external_id=external_id,
                title=title,
                company=company,
                city=location,
                salary_min_k=sal_min,
                salary_max_k=sal_max,
                salary_currency="USD",
                experience_years=str(raw.get("experienceLevel") or "") or None,
                education=str(raw.get("educationLevel") or "") or None,
                skills=skills,
                url=f"https://www.linkedin.com/jobs/view/{external_id}",
                posted_at=str(listed_at) if listed_at else None,
                description_snippet=(raw.get("description") or "")[:280] or None,
                raw=raw,
            )
        except Exception as exc:
            logger.debug("linkedin.parse error: %s raw=%s", exc, raw)
            return None

    # ------------------------------------------------------------------
    # get_salary_trend
    # ------------------------------------------------------------------
    @with_resilience(
        provider="job_market_linkedin",
        method="get_salary_trend",
        retry=RetryPolicy(max_retries=2, base_delay=1.0, max_delay=5.0),
        rate_per_sec=3.0,
        burst=5,
    )
    async def get_salary_trend(
        self,
        role: str,
        city: str,
        *,
        months: int = 12,
    ) -> list[SalaryPoint]:
        # LinkedIn 不公开历史薪资 → fallback
        return await self._fallback.get_salary_trend(role, city, months=months)

    # ------------------------------------------------------------------
    # get_hot_skills
    # ------------------------------------------------------------------
    @with_resilience(
        provider="job_market_linkedin",
        method="get_hot_skills",
        retry=RetryPolicy(max_retries=2, base_delay=1.0, max_delay=5.0),
        rate_per_sec=3.0,
        burst=5,
    )
    async def get_hot_skills(
        self,
        role: str | None = None,
        *,
        limit: int = 20,
    ) -> list[SkillDemand]:
        if not self._has_credentials():
            return await self._fallback.get_hot_skills(role, limit=limit)
        client = await self._get_client()
        try:
            resp = await client.get(
                "/analytics/jobPostings/skills",
                params={"q": "skills", "role": role or "", "limit": limit},
            )
        except httpx.HTTPError as exc:
            logger.warning("linkedin.hot_skills network error: %s → fallback", exc)
            return await self._fallback.get_hot_skills(role, limit=limit)
        if resp.status_code >= 400:
            return await self._fallback.get_hot_skills(role, limit=limit)
        try:
            payload = resp.json()
            items = payload.get("elements") or []
        except Exception:
            return await self._fallback.get_hot_skills(role, limit=limit)
        out: list[SkillDemand] = []
        for row in items:
            score = float(row.get("demandScore") or 0)
            out.append(SkillDemand(
                skill=str(row.get("name") or ""),
                demand_score=score,
                job_count=int(row.get("postingCount") or 0),
                growth_pct=(float(row["growth"]) if "growth" in row else None),
            ))
        out.sort(key=lambda s: s.demand_score, reverse=True)
        return out[:limit] or await self._fallback.get_hot_skills(role, limit=limit)


__all__ = ["LinkedInProvider"]