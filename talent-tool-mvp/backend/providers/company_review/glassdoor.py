"""Glassdoor CompanyReviewProvider (T2401).

Glassdoor OpenAPI:
    - 文档: https://www.glassdoor.com/developer (企业账号 + partner_id + key)
    - 鉴权: HTTP Header `Authorization: Bearer <token>`

降级策略:
    - 任何 ProviderError / 网络错误 → 自动 fallback 到 MockCompanyReviewProvider
    - 通过 `GLASSDOOR_API_KEY` 启用真实调用,缺失则直接走 mock
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

_GLASS_BASE = os.getenv("GLASSDOOR_API_BASE", "https://api.glassdoor.com/v1")
_GLASS_PARTNER_ID = os.getenv("GLASSDOOR_PARTNER_ID", "")
_GLASS_API_KEY = os.getenv("GLASSDOOR_API_KEY", "")
_GLASS_TIMEOUT = float(os.getenv("GLASSDOOR_TIMEOUT", "8.0"))


class GlassdoorProvider(CompanyReviewProvider):
    """Glassdoor provider; 凭证缺失或失败时自动 fallback 到 mock."""

    provider_name = "glassdoor"

    def __init__(self) -> None:
        self._api_key = _GLASS_API_KEY
        self._partner_id = _GLASS_PARTNER_ID
        self._mock = MockCompanyReviewProvider()
        self._has_real = bool(self._api_key and self._partner_id)

    def _params(self) -> dict:
        return {"partner.id": self._partner_id, "v": "1", "format": "json"}

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "User-Agent": "waibao/6.0",
        }

    @staticmethod
    def _company_id_for(company_id: str) -> str:
        return company_id.split(":", 1)[1] if ":" in company_id else company_id

    async def _fallback_rating(self, company_id: str) -> CompanyRating:
        r = await self._mock.get_company_reviews(company_id)
        # Glassdoor 评分体系略有不同 (overall 0-5 + recommend 0-100)
        return CompanyRating(
            source="glassdoor",
            score=r.score,
            review_count=r.review_count,
            recommend_pct=r.recommend_pct,
            ceo_pct=None,  # Glassdoor 无 CEO 维度
            breakdown=r.breakdown,
        )

    @with_resilience(
        provider="company_review_glassdoor",
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
            async with httpx.AsyncClient(timeout=_GLASS_TIMEOUT) as client:
                resp = await client.get(
                    f"{_GLASS_BASE}/company/{cid}",
                    params=self._params(),
                    headers=self._headers(),
                )
                if resp.status_code == 401:
                    raise AuthError("glassdoor auth failed", provider="glassdoor")
                if resp.status_code == 429:
                    raise QuotaExceededError("glassdoor quota", provider="glassdoor")
                if resp.status_code >= 500:
                    raise UpstreamUnavailableError(
                        f"glassdoor {resp.status_code}", provider="glassdoor"
                    )
                resp.raise_for_status()
                data = resp.json().get("response", {})
                return CompanyRating(
                    source="glassdoor",
                    score=float(data.get("overallRating", 0)),
                    review_count=int(data.get("numberOfReviews", 0)),
                    recommend_pct=float(data.get("recommendToFriend", 0)) * 100
                    if data.get("recommendToFriend") is not None
                    else None,
                    ceo_pct=None,
                    breakdown={
                        "compensation": float(data.get("compensationRating", 0)),
                        "culture": float(data.get("cultureAndValuesRating", 0)),
                        "management": float(data.get("managementRating", 0)),
                        "worklife": float(data.get("workLifeBalanceRating", 0)),
                    },
                )
        except ProviderError:
            raise
        except Exception as exc:
            logger.warning("glassdoor.rating_failed company=%s exc=%s -> fallback", cid, exc)
            return await self._fallback_rating(company_id)

    @with_resilience(
        provider="company_review_glassdoor",
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
            async with httpx.AsyncClient(timeout=_GLASS_TIMEOUT) as client:
                resp = await client.get(
                    f"{_GLASS_BASE}/company/{cid}/reviews",
                    params={**self._params(), "page": page, "pageSize": page_size},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json().get("response", {})
                return [
                    Review(
                        id=str(r.get("reviewId")),
                        source="glassdoor",
                        title=(r.get("reviewTitle") or "")[:120],
                        content=(r.get("pros") or "")[:500],
                        pros=r.get("pros"),
                        cons=r.get("cons"),
                        rating=float(r.get("overall") or 0),
                        job_title=r.get("jobTitle"),
                        employment_status=r.get("employmentStatus"),
                        created_at=r.get("reviewDateTime"),
                        author=r.get("authorNickname"),
                        helpful_count=int(r.get("helpfulCount", 0)),
                    )
                    for r in data.get("reviews", [])
                ]
        except Exception as exc:
            logger.warning("glassdoor.reviews_failed company=%s exc=%s -> fallback", cid, exc)
            return await self._mock.get_employee_reviews(
                company_id, page=page, page_size=page_size
            )

    @with_resilience(
        provider="company_review_glassdoor",
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
            async with httpx.AsyncClient(timeout=_GLASS_TIMEOUT) as client:
                resp = await client.get(
                    f"{_GLASS_BASE}/company/{cid}/interviews",
                    params={**self._params(), "page": page, "pageSize": page_size},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json().get("response", {})
                return [
                    InterviewExperience(
                        id=str(it.get("interviewId")),
                        source="glassdoor",
                        company_id=cid,
                        job_title=it.get("jobTitle", ""),
                        difficulty=int(it.get("difficulty", 3)),
                        experience=it.get("experience", "neutral"),
                        process=it.get("process"),
                        questions=it.get("questions") or [],
                        result=it.get("outcome", "pending"),
                        created_at=it.get("interviewDate"),
                        author=it.get("authorNickname"),
                    )
                    for it in data.get("interviews", [])
                ]
        except Exception as exc:
            logger.warning("glassdoor.interviews_failed company=%s exc=%s -> fallback", cid, exc)
            return await self._mock.get_interview_experiences(
                company_id, page=page, page_size=page_size
            )

    @with_resilience(
        provider="company_review_glassdoor",
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
            async with httpx.AsyncClient(timeout=_GLASS_TIMEOUT) as client:
                resp = await client.get(
                    f"{_GLASS_BASE}/company/{cid}/salary",
                    params=self._params(),
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json().get("response", {})
                return SalaryInsights(
                    company_id=cid,
                    median_k=float(data.get("medianBasePay", 0)) / 1000.0,
                    p25_k=float(data.get("p25BasePay", 0)) / 1000.0
                    if data.get("p25BasePay")
                    else None,
                    p75_k=float(data.get("p75BasePay", 0)) / 1000.0
                    if data.get("p75BasePay")
                    else None,
                    sample_size=int(data.get("salaryCount", 0)),
                    currency=data.get("currency", "USD"),
                    by_role={},
                    last_updated=data.get("lastUpdated"),
                )
        except Exception as exc:
            logger.warning("glassdoor.salary_failed company=%s exc=%s -> fallback", cid, exc)
            return await self._mock.get_salary_insights(company_id).get