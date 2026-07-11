"""拉勾网 JobMarketProvider 适配器 (T607).

拉勾 OpenAPI:
    - 文档: https://open.lagou.com/
    - 鉴权: OAuth2 client_credentials grant → `Authorization: Bearer <access_token>`
    - 主要接口:
        POST /v2/positions/search
        GET  /v2/positions/{id}
        GET  /v2/positions/salaryTrends
        GET  /v2/positions/hotKeywords

降级策略: 任何上游异常 / 鉴权失败 / 网络错误 → 自动 fallback 到 MockJobMarketProvider
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
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
from .boss_zhipin import _to_job_posting  # 共用 Boss 的解析器(结构相近)
from .mock import MockJobMarketProvider
from .types import JobPosting, SalaryPoint, SkillDemand

logger = logging.getLogger(__name__)

_LAGOU_BASE = os.getenv("JOB_MARKET_LAGOU_BASE", "https://openapi.lagou.com/v2")
_LAGOU_CLIENT_ID = os.getenv("JOB_MARKET_LAGOU_CLIENT_ID", "")
_LAGOU_CLIENT_SECRET = os.getenv("JOB_MARKET_LAGOU_CLIENT_SECRET", "")
_LAGOU_TIMEOUT = float(os.getenv("JOB_MARKET_LAGOU_TIMEOUT", "8.0"))


class _TokenCache:
    """OAuth2 access token 内存缓存,有效期 < 5 min,提前 60s 续期."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get(self, fetcher: "LagouProvider") -> str:
        async with self._lock:
            if self._token and time.monotonic() < self._expires_at - 60:
                return self._token
            token = await fetcher._fetch_token()
            if not token:
                raise AuthError("lagou token fetch returned empty", provider="lagou")
            self._token = token
            self._expires_at = time.monotonic() + 240  # 4 min
            return token


class LagouProvider(JobMarketProvider):
    """拉勾网适配器. 失败自动 fallback 到 MockJobMarketProvider."""

    provider_name = "lagou"

    def __init__(self, *, fallback: JobMarketProvider | None = None) -> None:
        self._fallback = fallback or MockJobMarketProvider()
        self._client: httpx.AsyncClient | None = None
        self._tokens = _TokenCache()

    def _has_credentials(self) -> bool:
        return bool(_LAGOU_CLIENT_ID and _LAGOU_CLIENT_SECRET)

    async def _get_client(self, with_auth: bool = True) -> httpx.AsyncClient:
        headers: dict[str, str] = {
            "User-Agent": "waibao/3.0 (+https://waibao.local)",
            "Content-Type": "application/json",
        }
        if with_auth and self._has_credentials():
            token = await self._tokens.get(self)
            headers["Authorization"] = f"Bearer {token}"
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=_LAGOU_BASE,
                timeout=_LAGOU_TIMEOUT,
                headers=headers,
            )
        else:
            # 更新 auth header
            self._client.headers.update(headers)
        return self._client

    async def _fetch_token(self) -> str | None:
        """OAuth2 client_credentials grant."""
        try:
            async with httpx.AsyncClient(timeout=_LAGOU_TIMEOUT) as c:
                resp = await c.post(
                    f"{_LAGOU_BASE}/oauth/token",
                    json={
                        "grant_type": "client_credentials",
                        "client_id": _LAGOU_CLIENT_ID,
                        "client_secret": _LAGOU_CLIENT_SECRET,
                    },
                )
        except httpx.HTTPError as exc:
            logger.warning("lagou.token network error: %s", exc)
            return None
        if resp.status_code != 200:
            logger.warning("lagou.token status=%s", resp.status_code)
            return None
        try:
            payload = resp.json()
        except Exception:
            return None
        return payload.get("access_token")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # search_jobs
    # ------------------------------------------------------------------
    @with_resilience(
        provider="job_market_lagou",
        method="search_jobs",
        retry=RetryPolicy(max_retries=2, base_delay=0.8, max_delay=4.0),
        rate_per_sec=5.0,
        burst=10,
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
        body: dict[str, Any] = {
            "keyword": keyword,
            "pageNo": page,
            "pageSize": page_size,
        }
        if city:
            body["city"] = city
        try:
            resp = await client.post("/positions/search", json=body)
        except httpx.HTTPError as exc:
            logger.warning("lagou.search network error: %s → fallback", exc)
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
            # token 失效,清空缓存重试一次
            self._tokens._token = None  # noqa: SLF001 — 测试可观察
            raise AuthError("lagou auth failed", provider="lagou")
        if resp.status_code == 402:
            raise QuotaExceededError("lagou quota exhausted", provider="lagou")
        if resp.status_code >= 500:
            raise UpstreamUnavailableError(
                f"lagou 5xx {resp.status_code}", provider="lagou",
            )
        try:
            payload = resp.json()
        except Exception as exc:
            raise UpstreamUnavailableError(
                f"lagou bad json: {exc}", provider="lagou",
            ) from exc
        data = payload.get("content") or payload.get("data") or {}
        rows = data.get("positionResult") or data.get("list") or []
        if not isinstance(rows, list):
            return []
        out: list[JobPosting] = []
        for raw in rows:
            # 拉勾字段名为 camelCase,转成 snake 后复用 Boss 解析器
            normalized = {
                "id": raw.get("positionId") or raw.get("id"),
                "title": raw.get("positionName") or raw.get("title"),
                "company": raw.get("companyName") or raw.get("company") or (raw.get("company") or {}).get("name"),
                "cityName": raw.get("city") or raw.get("cityName"),
                "salary": raw.get("salary") or {
                    "min": raw.get("salaryMin"),
                    "max": raw.get("salaryMax"),
                },
                "experience": raw.get("workYear") or raw.get("experience"),
                "education": raw.get("education"),
                "skills": raw.get("skill") or raw.get("skills") or raw.get("positionLables"),
                "url": raw.get("positionUrl") or raw.get("url"),
                "published_at": raw.get("createTime") or raw.get("published_at"),
                "description": raw.get("positionDesc") or raw.get("description"),
            }
            out.append(_to_job_posting(normalized))
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

    # ------------------------------------------------------------------
    # get_salary_trend
    # ------------------------------------------------------------------
    @with_resilience(
        provider="job_market_lagou",
        method="get_salary_trend",
        retry=RetryPolicy(max_retries=2, base_delay=0.8, max_delay=4.0),
        rate_per_sec=5.0,
        burst=10,
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
        try:
            resp = await client.get(
                "/positions/salaryTrends",
                params={"role": role, "city": city, "months": months},
            )
        except httpx.HTTPError as exc:
            logger.warning("lagou.salary_trend network error: %s → fallback", exc)
            return await self._fallback.get_salary_trend(role, city, months=months)
        if resp.status_code >= 400:
            return await self._fallback.get_salary_trend(role, city, months=months)
        try:
            payload = resp.json()
            series = (payload.get("content") or {}).get("list") or []
        except Exception:
            return await self._fallback.get_salary_trend(role, city, months=months)
        out: list[SalaryPoint] = []
        for row in series:
            median = float(row.get("avgSalary") or row.get("median") or 0)
            out.append(SalaryPoint(
                period=str(row.get("month") or row.get("period") or ""),
                median_k=median / 1000 if median > 200 else median,
                p25_k=(row.get("p25Salary") or None),
                p75_k=(row.get("p75Salary") or None),
                sample_size=(int(row.get("totalNum") or 0) or None),
                currency="CNY",
            ))
        return out or await self._fallback.get_salary_trend(role, city, months=months)

    # ------------------------------------------------------------------
    # get_hot_skills
    # ------------------------------------------------------------------
    @with_resilience(
        provider="job_market_lagou",
        method="get_hot_skills",
        retry=RetryPolicy(max_retries=2, base_delay=0.8, max_delay=4.0),
        rate_per_sec=5.0,
        burst=10,
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
                "/positions/hotKeywords",
                params={"role": role or "", "limit": limit},
            )
        except httpx.HTTPError as exc:
            logger.warning("lagou.hot_skills network error: %s → fallback", exc)
            return await self._fallback.get_hot_skills(role, limit=limit)
        if resp.status_code >= 400:
            return await self._fallback.get_hot_skills(role, limit=limit)
        try:
            payload = resp.json()
            items = (payload.get("content") or {}).get("list") or []
        except Exception:
            return await self._fallback.get_hot_skills(role, limit=limit)
        out: list[SkillDemand] = []
        for row in items:
            score = float(row.get("score") or row.get("hotIndex") or 0)
            out.append(SkillDemand(
                skill=str(row.get("keyword") or row.get("name") or ""),
                demand_score=score,
                job_count=int(row.get("count") or 0),
                growth_pct=(float(row["growth"]) if "growth" in row else None),
            ))
        out.sort(key=lambda s: s.demand_score, reverse=True)
        return out[:limit] or await self._fallback.get_hot_skills(role, limit=limit)


__all__ = ["LagouProvider"]