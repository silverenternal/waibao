"""Boss直聘 JobMarketProvider 适配器 (T607).

Boss直聘 OpenAPI:
    - 文档: https://www.zhipin.com/api/ (企业账号 + AppKey 才能开通)
    - 鉴权: HTTP Header `X-App-Key: <app_key>`
    - 沙箱: 沙箱环境数据有限,真实数据需生产 AppKey
    - 主要接口:
        GET /job/list            — 在招岗位检索
        GET /job/{id}/detail     — 岗位详情
        GET /job/salary/trend    — 历史薪资(企业版才有)

降级策略:
    - 任何 ProviderError / 网络错误 / 配额耗尽 → 自动 fallback 到 MockJobMarketProvider
    - 通过 `JOB_MARKET_BOSS_APP_KEY` 启用真实调用,缺失则直接走 mock
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
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

_BOSS_BASE = os.getenv("JOB_MARKET_BOSS_BASE", "https://openapi.zhipin.com/v1")
_BOSS_APP_KEY = os.getenv("JOB_MARKET_BOSS_APP_KEY", "")
_BOSS_TIMEOUT = float(os.getenv("JOB_MARKET_BOSS_TIMEOUT", "8.0"))


def _safe_float(x: Any) -> float | None:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


class BossZhipinProvider(JobMarketProvider):
    """Boss直聘适配器. 失败自动 fallback 到 MockJobMarketProvider."""

    provider_name = "boss"

    def __init__(self, *, fallback: JobMarketProvider | None = None) -> None:
        self._fallback = fallback or MockJobMarketProvider()
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=_BOSS_BASE,
                timeout=_BOSS_TIMEOUT,
                headers={
                    "X-App-Key": _BOSS_APP_APP_KEY(),  # type: ignore[arg-type]
                    "User-Agent": "waibao/3.0 (+https://waibao.local)",
                },
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _has_credentials(self) -> bool:
        return bool(_BOSS_APP_KEY)

    # ------------------------------------------------------------------
    # search_jobs
    # ------------------------------------------------------------------
    @with_resilience(
        provider="job_market_boss",
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
            logger.info("boss.missing_credentials → fallback")
            return await self._fallback.search_jobs(
                keyword, city=city, salary_range=salary_range,
                page=page, page_size=page_size,
            )

        client = await self._get_client()
        params: dict[str, Any] = {
            "query": keyword,
            "page": page,
            "pageSize": page_size,
        }
        if city:
            params["city"] = city
        try:
            resp = await client.get("/job/list", params=params)
        except httpx.HTTPError as exc:
            logger.warning("boss.search_jobs network error: %s → fallback", exc)
            return await self._fallback.search_jobs(
                keyword, city=city, salary_range=salary_range,
                page=page, page_size=page_size,
            )
        return self._parse_search(resp, salary_range)

    def _parse_search(
        self,
        resp: httpx.Response,
        salary_range: tuple[float, float] | None,
    ) -> list[JobPosting]:
        if resp.status_code == 401 or resp.status_code == 403:
            raise AuthError("boss auth failed", provider="boss")
        if resp.status_code == 402:
            raise QuotaExceededError("boss quota exhausted", provider="boss")
        if resp.status_code >= 500:
            raise UpstreamUnavailableError(
                f"boss 5xx {resp.status_code}", provider="boss",
            )
        try:
            payload = resp.json()
        except Exception as exc:
            raise UpstreamUnavailableError(
                f"boss bad json: {exc}", provider="boss",
            ) from exc
        data = payload.get("data") or payload.get("result") or {}
        items = data.get("jobs") or data.get("list") or []
        if not isinstance(items, list):
            logger.warning("boss.search_jobs unexpected payload shape → fallback")
            return []
        postings: list[JobPosting] = []
        for raw in items:
            postings.append(_to_job_posting(raw))
        if salary_range is not None:
            lo, hi = salary_range
            postings = [
                j for j in postings
                if j.salary_min_k is not None
                and j.salary_max_k is not None
                and j.salary_min_k >= lo
                and j.salary_max_k <= hi
            ]
        return postings

    # ------------------------------------------------------------------
    # get_salary_trend
    # ------------------------------------------------------------------
    @with_resilience(
        provider="job_market_boss",
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
                "/job/salary/trend",
                params={"role": role, "city": city, "months": months},
            )
        except httpx.HTTPError as exc:
            logger.warning("boss.salary_trend network error: %s → fallback", exc)
            return await self._fallback.get_salary_trend(role, city, months=months)
        if resp.status_code >= 400:
            logger.warning("boss.salary_trend status=%s → fallback", resp.status_code)
            return await self._fallback.get_salary_trend(role, city, months=months)
        try:
            payload = resp.json()
            series = (payload.get("data") or {}).get("series") or []
        except Exception:
            return await self._fallback.get_salary_trend(role, city, months=months)
        out: list[SalaryPoint] = []
        for row in series:
            out.append(SalaryPoint(
                period=str(row.get("period") or ""),
                median_k=_safe_float(row.get("median")) or 0.0,
                p25_k=_safe_float(row.get("p25")),
                p75_k=_safe_float(row.get("p75")),
                sample_size=int(row.get("sample_size") or 0) or None,
                currency="CNY",
            ))
        return out or await self._fallback.get_salary_trend(role, city, months=months)

    # ------------------------------------------------------------------
    # get_hot_skills
    # ------------------------------------------------------------------
    @with_resilience(
        provider="job_market_boss",
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
                "/job/skill/hot",
                params={"role": role or "", "limit": limit},
            )
        except httpx.HTTPError as exc:
            logger.warning("boss.hot_skills network error: %s → fallback", exc)
            return await self._fallback.get_hot_skills(role, limit=limit)
        if resp.status_code >= 400:
            return await self._fallback.get_hot_skills(role, limit=limit)
        try:
            payload = resp.json()
            items = (payload.get("data") or {}).get("list") or []
        except Exception:
            return await self._fallback.get_hot_skills(role, limit=limit)
        out: list[SkillDemand] = []
        for row in items:
            score = _safe_float(row.get("score")) or 0.0
            out.append(SkillDemand(
                skill=str(row.get("name") or ""),
                demand_score=score,
                job_count=int(row.get("count") or 0),
                growth_pct=_safe_float(row.get("growth")),
            ))
        out.sort(key=lambda s: s.demand_score, reverse=True)
        return out[:limit] or await self._fallback.get_hot_skills(role, limit=limit)


def _to_job_posting(raw: dict[str, Any]) -> JobPosting:
    salary = raw.get("salary") or {}
    smin = _safe_float(salary.get("min"))
    smax = _safe_float(salary.get("max"))
    skills_raw = raw.get("skills") or raw.get("labels") or []
    if isinstance(skills_raw, str):
        skills = [s.strip() for s in skills_raw.split(",") if s.strip()]
    elif isinstance(skills_raw, list):
        skills = [str(s) for s in skills_raw]
    else:
        skills = []
    posted_at = raw.get("published_at") or raw.get("publishTime")
    try:
        if isinstance(posted_at, (int, float)):
            posted_iso = datetime.fromtimestamp(
                int(posted_at), tz=timezone.utc,
            ).isoformat()
        elif isinstance(posted_at, str):
            posted_iso = posted_at
        else:
            posted_iso = None
    except Exception:
        posted_iso = None
    return JobPosting(
        source="boss",
        external_id=str(raw.get("id") or raw.get("jobId") or ""),
        title=str(raw.get("title") or raw.get("jobName") or ""),
        company=str(raw.get("company") or raw.get("brandName") or ""),
        city=raw.get("cityName") or raw.get("city"),
        salary_min_k=smin,
        salary_max_k=smax,
        salary_currency="CNY",
        experience_years=raw.get("experience"),
        education=raw.get("education"),
        skills=skills,
        url=raw.get("url") or raw.get("link"),
        posted_at=posted_iso,
        description_snippet=(raw.get("description") or "")[:280] or None,
        raw=raw,
    )


def _BOSS_APP_APP_KEY() -> str:
    """兼容某些 linter 对全局 _BOSS_APP_KEY 的访问."""
    return _BOSS_APP_KEY


__all__ = ["BossZhipinProvider"]