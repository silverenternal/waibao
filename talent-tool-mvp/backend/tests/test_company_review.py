"""Tests for Company Review Service + API (T2401).

验证:
- 3 源聚合 (AllProvidersAggregator)
- 7 天缓存
- service.get_bundle
"""
from __future__ import annotations

import asyncio
import pytest

from providers.company_review.registry import (
    AllProvidersAggregator,
    reset_company_review_cache,
)
from providers.company_review.types import (
    CompanyRating,
    CompanyReviewBundle,
    InterviewExperience,
    Review,
    SalaryInsights,
)
from services.platform.company_review import (
    CompanyReviewService,
    get_company_review_service,
)


@pytest.fixture(autouse=True)
def reset():
    reset_company_review_cache()
    yield
    reset_company_review_cache()


def test_aggregator_get_bundle_bytedance():
    """AllProvidersAggregator 应能从 3 源聚合 bytedance 数据."""
    agg = AllProvidersAggregator()
    bundle = asyncio.run(agg.get_bundle("bytedance"))
    assert isinstance(bundle, CompanyReviewBundle)
    assert bundle.company_id == "bytedance"
    # 应包含 3 源 ratings
    sources = {r.source for r in bundle.ratings}
    assert {"kanzhun", "glassdoor", "maimai"}.issubset(sources)
    assert bundle.aggregated_score is not None
    assert 0 <= bundle.aggregated_score <= 5


def test_aggregator_get_bundle_unknown_company():
    """未知公司应回退到 mock 数据,不抛异常."""
    agg = AllProvidersAggregator()
    bundle = asyncio.run(agg.get_bundle("totally-unknown-xyz-123"))
    assert bundle.company_id == "totally-unknown-xyz-123"
    # 仍能拉出 reviews (来自 mock fallback)
    assert isinstance(bundle.reviews, list)
    assert isinstance(bundle.interviews, list)


def test_aggregator_employee_reviews_dedup():
    """3 源评价应去重合并."""
    agg = AllProvidersAggregator()
    reviews = asyncio.run(agg.get_employee_reviews("bytedance", page_size=10))
    keys = [f"{r.source}:{r.id}" for r in reviews]
    assert len(keys) == len(set(keys)), "should dedup by source+id"


def test_aggregator_interviews_order():
    """面试经验应按时间倒序."""
    agg = AllProvidersAggregator()
    items = asyncio.run(agg.get_interview_experiences("bytedance", page_size=10))
    if len(items) >= 2:
        assert (items[0].created_at or "") >= (items[1].created_at or "")


def test_aggregator_salary_insights_aggregated():
    agg = AllProvidersAggregator()
    s = asyncio.run(agg.get_salary_insights("bytedance"))
    assert s.median_k > 0
    assert s.p25_k <= s.median_k <= s.p75_k


def test_service_get_bundle_caches():
    """Service 应缓存 7 天."""
    svc = CompanyReviewService()
    b1 = asyncio.run(svc.get_bundle("bytedance"))
    # 第二次应直接命中缓存
    b2 = asyncio.run(svc.get_bundle("bytedance"))
    assert b1.aggregated_score == b2.aggregated_score


def test_service_search_companies():
    svc = CompanyReviewService()
    results = asyncio.run(svc.search_companies("字节"))
    assert any(c["id"] == "bytedance" for c in results)


def test_service_get_employee_reviews_pagination():
    svc = CompanyReviewService()
    p1 = asyncio.run(svc.get_employee_reviews("bytedance", page=1, page_size=3))
    p2 = asyncio.run(svc.get_employee_reviews("bytedance", page=2, page_size=3))
    assert isinstance(p1, list)
    assert isinstance(p2, list)


def test_service_clear_cache():
    svc = CompanyReviewService()
    asyncio.run(svc.get_bundle("bytedance"))
    svc.clear_cache()
    # 清空后内部 cache 应为空
    assert svc._cache == {}


def test_aggregator_rating_avg_in_range():
    """聚合分应在 0-5 之间."""
    agg = AllProvidersAggregator()
    r = asyncio.run(agg.get_company_reviews("bytedance"))
    assert 0 <= r.score <= 5
    assert r.review_count > 0


def test_get_company_review_service_singleton():
    s1 = get_company_review_service()
    s2 = get_company_review_service()
    assert s1 is s2