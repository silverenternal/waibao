"""Maimai (脉脉) CompanyReviewProvider (T2401).

脉脉 OpenAPI:
    - 文档: https://maimai.cn/openapi (企业账号 + access_token)
    - 鉴权: HTTP Header `Authorization: Bearer <access_token>`

降级策略:
    - 任何 ProviderError / 网络错误 → 自动 fallback 到 MockCompanyReviewProvider
    - 通过 `MAIMAI_ACCESS_TOKEN` 启用真实调用,缺失则直接走 mock
"""
from __future__ import annotations

import logging
import os

import httpx

from ..base import RetryPolicy, with_resilience
from ..exceptions import (
    AuthError,
    ProviderError,
    QuotaExceededError,
    UpstreamUnavailableError,
)
from .base import CompanyReviewProvider
from .mock import MockCompanyReviewProvider
from .types import (
    CompanyRating,
    InterviewExperience,
    Review,
    SalaryInsights,
)

logger = logging.getLogger(__name__)

_MAIMAI_BASE = os.getenv("MAIMAI_API_BASE", "https://openapi.maimai.cn/v1")
_MAIMAI_TOKEN = os.getenv("MAIMAI_ACCESS_TOKEN", "")
_MAIMAI_TIMEOUT = float(os.getenv("MAIMAI_TIMEOUT", "8.0"))


class MaimaiProvider(CompanyReviewProvider):
    """脉脉 provider; 凭证缺失或失败时自动 fallback 到 mock."""

    provider_name = "maimai"

    def __init__(self) -> None:
        self._token = _MAIMAI_TOKEN
        self._mock = MockCompanyReviewProvider()
        self._has_real = bool(self._token)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "User-Agent": "waibao/6.0",
        }

    @staticmethod
    def _company_id_for(company_id: str) -> str:
        return company_id.split(":", 1)[1] if ":" in company_id else company_id

    async def _fallback_rating(self, company_id: str) -> CompanyRating:
        r = await self._mock.get_company_reviews(company_id)
        return CompanyRating(
            source="maimai",
            score=r.score,
            review_count=r.review_count,
            recommend_pct=r.recommend_pct,
            ceo_pct=None,  # 脉脉无 CEO 维度
            breakdown=r.breakdown,
        )

    @with_resilience(
        provider="company_review_maimai",
        method="get_company_reviews",
        retry=RetryPolicy(max_retries=2, base_delay=0.5),
        rate_per_sec=5.0,
        burst=10,
    )
    async def get_company_reviews(self, company_id: str) -> CompanyRating:
        if not self._has_real:
            return await self._fallback_rating(company_id)
        cid = self._company_id_for(company_id)
        try:
            async with httpx.AsyncClient(timeout=_MAIMAI_TIMEOUT) as client:
                resp = await client.get(
                    f"{_MAIMAI_BASE}/company/{cid}/rating",
                    headers=self._headers(),
                )
                if resp.status_code == 401:
                    raise AuthError("maimai auth failed", provider="maimai")
                if resp.status_code == 429:
                    raise QuotaExceededError("maimai quota", provider="maimai")
                if resp.status_code >= 500:
                    raise UpstreamUnavailableError(
                        f"maimai {resp.status_code}", provider="maimai"
                    )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                return CompanyRating(
                    source="maimai",
                    score=float(data.get("score", 0)),
                    review_count=int(data.get("review_count", 0)),
                    recommend_pct=data.get("recommend_pct"),
                    ceo_pct=None,
                    breakdown=data.get("breakdown") or {},
                )
        except ProviderError:
            raise
        except Exception as exc:
            logger.warning("maimai.rating_failed company=%s exc=%s -> fallback", cid, exc)
            return await self._fallback_rating(company_id)

    @with_resilience(
        provider="company_review_maimai",
        method="get_employee_reviews",
        retry=RetryPolicy(max_retries=2, base_delay=0.5),
        rate_per_sec=5.0,
        burst=10,
    )
    async def get_employee_reviews(
        self,
        company_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> list:
        if not self._has_real:
            return await self._mock.get_employee_reviews(
                company_id, page=page, page_size=page_size
            )
        cid = self._company_id_for(company_id)
        try:
            async with httpx.AsyncClient(timeout=_MAIMAI_TIMEOUT) as client:
                resp = await client.get(
                    f"{_MAIMAI_BASE}/company/{cid}/reviews",
                    params={"page": page, "page_size": page_size},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                return [
                    Review(
                        id=str(r.get("id")),
                        source="maimai",
                        title=r.get("title", ""),
                        content=(r.get("content") or "")[:500],
                        pros=r.get("pros"),
                        cons=r.get("cons"),
                        rating=float(r.get("rating", 0)),
                        job_title=r.get("position"),
                        employment_status=r.get("status"),
                        created_at=r.get("created_at"),
                        author=r.get("user_name"),
                        helpful_count=int(r.get("like_count", 0)),
                    )
                    for r in data.get("list", [])
                ]
        except Exception as exc:
            logger.warning("maimai.reviews_failed company=%s exc=%s -> fallback", cid, exc)
            return await self._mock.get_employee_reviews(
                company_id, page=page, page_size=page_size
            )

    @with_resilience(
        provider="company_review_maimai",
        method="get_interview_experiences",
        retry=RetryPolicy(max_retries=2, base_delay=0.5),
        rate_per_sec=5.0,
        burst=10,
    )
    async def get_interview_experiences(
        self,
        company_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> list:
        if not self._has_real:
            return await self._mock.get_interview_experiences(
                company_id, page=page, page_size=page_size
            )
        cid = self._company_id_for(company_id)
        try:
            async with httpx.AsyncClient(timeout=_MAIMAI_TIMEOUT) as client:
                resp = await client.get(
                    f"{_MAIMAI_BASE}/company/{cid}/interviews",
                    params={"page": page, "page_size": page_size},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                return [
                    InterviewExperience(
                        id=str(it.get("id")),
                        source="maimai",
                        company_id=cid,
                        job_title=it.get("position", ""),
                        difficulty=int(it.get("difficulty", 3)),
                        experience=it.get("experience", "neutral"),
                        process=it.get("process"),
                        questions=it.get("questions") or [],
                        result=it.get("result", "pending"),
                        created_at=it.get("created_at"),
                        author=it.get("user_name"),
                    )
                    for it in data.get("list", [])
                ]
        except Exception as exc:
            logger.warning("maimai.interviews_failed company=%s exc=%s -> fallback", cid, exc)
            return await self._mock.get_interview_experiences(
                company_id, page=page, page_size=page_size
            )

    @with_resilience(
        provider="company_review_maimai",
        method="get_salary_insights",
        retry=RetryPolicy(max_retries=2, base_delay=0.5),
        rate_per_sec=5.0,
        burst=10,
    )
    async def get_salary_insights(self, company_id: str) -> SalaryInsights:
        if not self._has_real:
            return await self._mock.get_salary_insights(company_id)
        cid = self._company_id_for(company_id)
        try:
            async with httpx.AsyncClient(timeout=_MAIMAI_TIMEOUT) as client:
                resp = await client.get(
                    f"{_MAIMAI_BASE}/company/{cid}/salary",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                return SalaryInsights(
                    company_id=cid,
                    median_k=float(data.get("median", 0)),
                    p25_k=data.get("p25"),
                    p75_k=data.get("p75"),
                    sample_size=int(data.get("count", 0)),
                    currency=data.get("currency", "CNY"),
                    by_role=data.get("by_position") or {},
                    last_updated=data.get("updated_at"),
                )
        except Exception as exc:
            logger.warning("maimai.salary_failed company=%s exc=%s -> fallback", cid, exc)
            return await self._mock.get_salary_insights(company_id)