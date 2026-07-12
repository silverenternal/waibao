"""Company Review Aggregation Service (T2401).

聚合 3 大公司评价数据源 (kanzhun / glassdoor / maimai):
- 内存缓存 7 天,降低外部调用频率
- 失败源自动 fallback 到 mock
- 统一返回 CompanyReviewBundle (3 源合一)
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from providers.company_review.registry import (
    AllProvidersAggregator,
    get_company_review_provider,
)
from providers.company_review.types import (
    CompanyRating,
    CompanyReviewBundle,
    InterviewExperience,
    Review,
    SalaryInsights,
)

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 7 * 24 * 3600.0  # 7 天


class CompanyReviewService:
    """聚合 3 源 + 7 天缓存.

    使用场景:
        - 求职者浏览公司详情页 (3 源评分 + 评价 + 面试经验 + 薪资洞察)
        - 公司搜索页 (按名称模糊查询)
        - HR dashboard (按公司聚合)
    """

    def __init__(self) -> None:
        self._provider = get_company_review_provider()
        self._cache: dict[str, tuple[float, Any]] = {}

    def _cache_get(self, key: str) -> Any | None:
        item = self._cache.get(key)
        if item is None:
            return None
        ts, value = item
        if time.monotonic() - ts > _CACHE_TTL_SEC:
            self._cache.pop(key, None)
            return None
        return value

    def _cache_put(self, key: str, value: Any) -> None:
        self._cache[key] = (time.monotonic(), value)

    async def get_bundle(self, company_id: str) -> CompanyReviewBundle:
        """获取聚合后的公司评价包 (含 3 源 ratings/reviews/interviews/salary).

        Args:
            company_id: 公司 ID (跨源统一 slug, 例如 'bytedance').

        Returns:
            CompanyReviewBundle,含聚合评分 + 评价 + 面试经验 + 薪资洞察.
        """
        cache_key = f"bundle::{company_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        # 优先使用 aggregator
        if isinstance(self._provider, AllProvidersAggregator):
            bundle = await self._provider.get_bundle(company_id)
        else:
            # 单 provider 模式 - 4 个维度独立拉取
            rating, reviews, interviews, salary = await asyncio.gather(
                self._provider.get_company_reviews(company_id),
                self._provider.get_employee_reviews(company_id, page_size=10),
                self._provider.get_interview_experiences(company_id, page_size=10),
                self._provider.get_salary_insights(company_id),
                return_exceptions=True,
            )
            ratings = [rating] if isinstance(rating, CompanyRating) else []
            reviews_list = reviews if isinstance(reviews, list) else []
            interviews_list = interviews if isinstance(interviews, list) else []
            salary_obj = salary if isinstance(salary, SalaryInsights) else None
            bundle = CompanyReviewBundle(
                company_id=company_id,
                ratings=ratings,
                reviews=reviews_list,
                interviews=interviews_list,
                salary=salary_obj,
                aggregated_score=ratings[0].score if ratings else None,
            )

        self._cache_put(cache_key, bundle)
        return bundle

    async def get_employee_reviews(
        self,
        company_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> list[Review]:
        cache_key = f"reviews::{company_id}::{page}::{page_size}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        result = await self._provider.get_employee_reviews(
            company_id, page=page, page_size=page_size
        )
        self._cache_put(cache_key, result)
        return result

    async def get_interview_experiences(
        self,
        company_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> list[InterviewExperience]:
        cache_key = f"interviews::{company_id}::{page}::{page_size}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        result = await self._provider.get_interview_experiences(
            company_id, page=page, page_size=page_size
        )
        self._cache_put(cache_key, result)
        return result

    async def get_salary_insights(self, company_id: str) -> SalaryInsights:
        cache_key = f"salary::{company_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        result = await self._provider.get_salary_insights(company_id)
        self._cache_put(cache_key, result)
        return result

    async def search_companies(self, query: str, *, limit: int = 20) -> list[dict]:
        """按名称模糊搜索 (走 mock 数据, 不缓存)."""
        from providers.company_review.mock import MockCompanyReviewProvider

        mock = MockCompanyReviewProvider()
        return mock.search_companies(query, limit=limit)

    def clear_cache(self) -> None:
        """清空缓存 (管理用)."""
        self._cache.clear()


_singleton: CompanyReviewService | None = None


def get_company_review_service() -> CompanyReviewService:
    """单例获取 CompanyReviewService."""
    global _singleton
    if _singleton is None:
        _singleton = CompanyReviewService()
    return _singleton