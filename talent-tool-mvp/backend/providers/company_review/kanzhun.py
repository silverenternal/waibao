"""Kanzhun (看准网) CompanyReviewProvider (T2401)."""
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

_KANZHUN_BASE = os.getenv("KANZHUN_API_BASE", "https://open.kanzhun.com/api/v1")
_KANZHUN_API_KEY = os.getenv("KANZHUN_API_KEY", "")
_KANZHUN_TIMEOUT = float(os.getenv("KANZHUN_TIMEOUT", "8.0"))


class KanzhunProvider(CompanyReviewProvider):
    """看准网 provider; 凭证缺失或失败时自动 fallback 到 mock."""

    provider_name = "kanzhun"

    def __init__(self) -> None:
        self._api_key = _KANZHUN_API_KEY
        self._mock = MockCompanyReviewProvider()
        self._has_real = bool(self._api_key)

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
        return CompanyRating(
            source="kanzhun",
            score=r.score,
            review_count=r.review_count,
            recommend_pct=r.recommend_pct,
            ceo_pct=r.ceo_pct,
            breakdown=r.breakdown,
        )

    @with_resilience(
        provider="company_review_kanzhun",
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
            async with httpx.AsyncClient(timeout=_KANZHUN_TIMEOUT) as client:
                resp = await client.get(
                    f"{_KANZHUN_BASE}/company/{cid}/rating",
                    headers=self._headers(),
                )
                if resp.status_code == 401:
                    raise AuthError("kanzhun auth failed", provider="kanzhun")
                if resp.status_code == 429:
                    raise QuotaExceededError("kanzhun quota", provider="kanzhun")
                if resp.status_code >= 500:
                    raise UpstreamUnavailableError(
                        f"kanzhun {resp.status_code}", provider="kanzhun"
                    )
                resp.raise_for_status()
                data = resp.json()
                return CompanyRating(
                    source="kanzhun",
                    score=float(data.get("score", 0)),
                    review_count=int(data.get("review_count", 0)),
                    recommend_pct=data.get("recommend_pct"),
                    ceo_pct=data.get("ceo_pct"),
                    breakdown=data.get("breakdown") or {},
                )
        except ProviderError:
            raise
        except Exception as exc:
            logger.warning("kanzhun.rating_failed company=%s exc=%s -> fallback", cid, exc)
            return await self._fallback_rating(company_id)

    @with_resilience(
        provider="company_review_kanzhun",
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
            async with httpx.AsyncClient(timeout=_KANZHUN_TIMEOUT) as client:
                resp = await client.get(
                    f"{_KANZHUN_BASE}/company/{cid}/reviews",
                    params={"page": page, "page_size": page_size},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                return [
                    Review(
                        id=str(r.get("id")),
                        source="kanzhun",
                        title=r.get("title", ""),
                        content=(r.get("content") or "")[:500],
                        pros=r.get("pros"),
                        cons=r.get("cons"),
                        rating=float(r.get("rating", 0)),
                        job_title=r.get("job_title"),
                        employment_status=r.get("employment_status"),
                        created_at=r.get("created_at"),
                        author=r.get("author"),
                        helpful_count=int(r.get("helpful_count", 0)),
                    )
                    for r in data.get("items", [])
                ]
        except Exception as exc:
            logger.warning("kanzhun.reviews_failed company=%s exc=%s -> fallback", cid, exc)
            return await self._mock.get_employee_reviews(
                company_id, page=page, page_size=page_size
            )

    @with_resilience(
        provider="company_review_kanzhun",
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
            async with httpx.AsyncClient(timeout=_KANZHUN_TIMEOUT) as client:
                resp = await client.get(
                    f"{_KANZHUN_BASE}/company/{cid}/interviews",
                    params={"page": page, "page_size": page_size},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                return [
                    InterviewExperience(
                        id=str(it.get("id")),
                        source="kanzhun",
                        company_id=cid,
                        job_title=it.get("job_title", ""),
                        difficulty=int(it.get("difficulty", 3)),
                        experience=it.get("experience", "neutral"),
                        process=it.get("process"),
                        questions=it.get("questions") or [],
                        result=it.get("result", "pending"),
                        created_at=it.get("created_at"),
                        author=it.get("author"),
                    )
                    for it in data.get("items", [])
                ]
        except Exception as exc:
            logger.warning("kanzhun.interviews_failed company=%s exc=%s -> fallback", cid, exc)
            return await self._mock.get_interview_experiences(
                company_id, page=page, page_size=page_size
            )

    @with_resilience(
        provider="company_review_kanzhun",
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
            async with httpx.AsyncClient(timeout=_KANZHUN_TIMEOUT) as client:
                resp = await client.get(
                    f"{_KANZHUN_BASE}/company/{cid}/salary",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                return SalaryInsights(
                    company_id=cid,
                    median_k=float(data.get("median_k", 0)),
                    p25_k=data.get("p25_k"),
                    p75_k=data.get("p75_k"),
                    sample_size=int(data.get("sample_size", 0)),
                    currency=data.get("currency", "CNY"),
                    by_role=data.get("by_role") or {},
                    last_updated=data.get("last_updated"),
                )
        except Exception as exc:
            logger.warning("kanzhun.salary_failed company=%s exc=%s -> fallback", cid, exc)
            return await self._mock.get_salary_insights(company_id)