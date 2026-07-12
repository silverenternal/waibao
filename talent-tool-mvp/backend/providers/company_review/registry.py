"""Company Review Provider 注册中心 (T2401).

根据 `COMPANY_REVIEW_PROVIDER` 环境变量选择具体实现:
    - mock      → MockCompanyReviewProvider  (默认,无需凭证)
    - kanzhun   → KanzhunProvider            (KANZHUN_API_KEY)
    - glassdoor → GlassdoorProvider          (GLASSDOOR_PARTNER_ID/GLASSDOOR_API_KEY)
    - maimai    → MaimaiProvider             (MAIMAI_ACCESS_TOKEN)
    - all       → AllProvidersAggregator     (并行调用 3 源,聚合)

所有真实 provider 在缺失凭证 / 上游失败时都会自动 fallback 到 mock.
"""
from __future__ import annotations

import asyncio
import logging
import os
from threading import Lock

from ..exceptions import InvalidRequestError
from .base import CompanyReviewProvider
from .glassdoor import GlassdoorProvider
from .kanzhun import KanzhunProvider
from .maimai import MaimaiProvider
from .mock import MockCompanyReviewProvider
from .types import (
    CompanyRating,
    CompanyReviewBundle,
    InterviewExperience,
    Review,
    SalaryInsights,
)

logger = logging.getLogger(__name__)

_provider: object | None = None
_lock = Lock()


class AllProvidersAggregator(CompanyReviewProvider):
    """并行调用 kanzhun / glassdoor / maimai, 聚合为 CompanyReviewBundle.

    任一 provider 失败不影响其他, 失败的源会被记录在 raw dict 里.
    """

    provider_name = "all"

    def __init__(self) -> None:
        self.kanzhun = KanzhunProvider()
        self.glassdoor = GlassdoorProvider()
        self.maimai = MaimaiProvider()
        self.mock = MockCompanyReviewProvider()

    async def get_company_reviews(self, company_id: str) -> CompanyRating:
        # 聚合多个 provider 的 rating 到一个综合评分
        results = await asyncio.gather(
            self.kanzhun.get_company_reviews(company_id),
            self.glassdoor.get_company_reviews(company_id),
            self.maimai.get_company_reviews(company_id),
            return_exceptions=True,
        )
        valid: list[CompanyRating] = []
        for r in results:
            if isinstance(r, CompanyRating):
                valid.append(r)
        if not valid:
            return await self.mock.get_company_reviews(company_id)
        avg = sum(r.score for r in valid) / len(valid)
        total_reviews = sum(r.review_count for r in valid)
        return CompanyRating(
            source="aggregated",
            score=round(avg, 2),
            review_count=total_reviews,
            recommend_pct=round(
                sum(r.recommend_pct or 0 for r in valid) / len(valid), 1
            ),
            ceo_pct=next((r.ceo_pct for r in valid if r.ceo_pct is not None), None),
            breakdown={},
        )

    async def get_employee_reviews(
        self,
        company_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> list[Review]:
        results = await asyncio.gather(
            self.kanzhun.get_employee_reviews(company_id, page=page, page_size=page_size),
            self.glassdoor.get_employee_reviews(company_id, page=page, page_size=page_size),
            self.maimai.get_employee_reviews(company_id, page=page, page_size=page_size),
            return_exceptions=True,
        )
        merged: list[Review] = []
        seen: set[str] = set()
        for r in results:
            if isinstance(r, list):
                for item in r:
                    key = f"{item.source}:{item.id}"
                    if key in seen:
                        continue
                    seen.add(key)
                    merged.append(item)
        merged.sort(key=lambda x: x.created_at or "", reverse=True)
        return merged[:page_size]

    async def get_interview_experiences(
        self,
        company_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> list[InterviewExperience]:
        results = await asyncio.gather(
            self.kanzhun.get_interview_experiences(company_id, page=page, page_size=page_size),
            self.glassdoor.get_interview_experiences(company_id, page=page, page_size=page_size),
            self.maimai.get_interview_experiences(company_id, page=page, page_size=page_size),
            return_exceptions=True,
        )
        merged: list[InterviewExperience] = []
        seen: set[str] = set()
        for r in results:
            if isinstance(r, list):
                for item in r:
                    key = f"{item.source}:{item.id}"
                    if key in seen:
                        continue
                    seen.add(key)
                    merged.append(item)
        merged.sort(key=lambda x: x.created_at or "", reverse=True)
        return merged[:page_size]

    async def get_salary_insights(self, company_id: str) -> SalaryInsights:
        results = await asyncio.gather(
            self.kanzhun.get_salary_insights(company_id),
            self.glassdoor.get_salary_insights(company_id),
            self.maimai.get_salary_insights(company_id),
            return_exceptions=True,
        )
        valid: list[SalaryInsights] = []
        for r in results:
            if isinstance(r, SalaryInsights):
                valid.append(r)
        if not valid:
            return await self.mock.get_salary_insights(company_id)
        avg = sum(s.median_k for s in valid) / len(valid)
        return SalaryInsights(
            company_id=company_id,
            median_k=round(avg, 1),
            p25_k=round(sum(s.p25_k or s.median_k * 0.8 for s in valid) / len(valid), 1),
            p75_k=round(sum(s.p75_k or s.median_k * 1.2 for s in valid) / len(valid), 1),
            sample_size=sum(s.sample_size for s in valid),
            currency=valid[0].currency,
            by_role={},
            last_updated=valid[0].last_updated,
        )

    async def get_bundle(self, company_id: str) -> CompanyReviewBundle:
        """一键拉取所有维度数据."""
        rating, reviews, interviews, salary = await asyncio.gather(
            self.get_company_reviews(company_id),
            self.get_employee_reviews(company_id, page_size=10),
            self.get_interview_experiences(company_id, page_size=10),
            self.get_salary_insights(company_id),
        )
        # 单独再拉每个源的 rating 用于详情页
        all_ratings = await asyncio.gather(
            self.kanzhun.get_company_reviews(company_id),
            self.glassdoor.get_company_reviews(company_id),
            self.maimai.get_company_reviews(company_id),
            return_exceptions=True,
        )
        ratings = [r for r in all_ratings if isinstance(r, CompanyRating)]
        return CompanyReviewBundle(
            company_id=company_id,
            ratings=ratings,
            reviews=reviews,
            interviews=interviews,
            salary=salary,
            aggregated_score=rating.score,
        )


def get_company_review_provider() -> CompanyReviewProvider:
    """根据 COMPANY_REVIEW_PROVIDER env 返回对应 CompanyReviewProvider 实例."""
    global _provider
    if _provider is not None:
        return _provider  # type: ignore[return-value]
    with _lock:
        if _provider is not None:
            return _provider  # type: ignore[return-value]
        name = (os.getenv("COMPANY_REVIEW_PROVIDER") or "all").lower()
        if name == "all":
            logger.info("company_review.provider=all (aggregator)")
            _provider = AllProvidersAggregator()
        elif name == "mock":
            logger.info("company_review.provider=mock")
            _provider = MockCompanyReviewProvider()
        else:
            # 单 provider 模式 - 通过 _build_provider 处理
            _provider = _build_provider(name)
        return _provider  # type: ignore[return-value]


def _build_provider(name: str) -> CompanyReviewProvider:
    try:
        if name == "kanzhun":
            from .kanzhun import KanzhunProvider
            logger.info("company_review.provider=kanzhun")
            return KanzhunProvider()
        if name == "glassdoor":
            from .glassdoor import GlassdoorProvider
            logger.info("company_review.provider=glassdoor")
            return GlassdoorProvider()
        if name == "maimai":
            from .maimai import MaimaiProvider
            logger.info("company_review.provider=maimai")
            return MaimaiProvider()
    except Exception as exc:  # pragma: no cover - 防御性
        logger.exception("company_review.provider=%s init failed -> mock", exc)
        return MockCompanyReviewProvider()

    raise InvalidRequestError(
        f"unknown COMPANY_REVIEW_PROVIDER={name}",
        details={
            "supported": ["all", "mock", "kanzhun", "glassdoor", "maimai"],
        },
    )


def reset_company_review_cache() -> None:
    """清空单例,主要用于单元测试."""
    global _provider
    with _lock:
        _provider = None