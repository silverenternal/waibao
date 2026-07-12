"""Tests for MockCompanyReviewProvider (T2401)."""
from __future__ import annotations

import asyncio

import pytest

from providers.company_review.mock import (
    MockCompanyReviewProvider,
    _MOCK_COMPANIES,
)


@pytest.fixture
def provider():
    return MockCompanyReviewProvider()


def test_list_companies_count():
    """Mock 数据池应 >= 50 家公司."""
    mock = MockCompanyReviewProvider()
    companies = mock.list_companies()
    assert len(companies) >= 50, f"expected 50+, got {len(companies)}"
    assert all("id" in c and "name" in c and "industry" in c for c in companies)


def test_search_companies_exact_match():
    mock = MockCompanyReviewProvider()
    results = mock.search_companies("字节跳动")
    assert any(c["id"] == "bytedance" for c in results)


def test_search_companies_partial_match():
    mock = MockCompanyReviewProvider()
    results = mock.search_companies("Tencent")
    assert len(results) >= 1


def test_search_companies_no_match():
    mock = MockCompanyReviewProvider()
    results = mock.search_companies("nonexistent-company-xyz-123")
    assert results == []


def test_search_companies_limit():
    mock = MockCompanyReviewProvider()
    results = mock.search_companies("公司", limit=5)
    assert len(results) <= 5


def test_get_company_reviews_known(provider):
    r = asyncio.run(provider.get_company_reviews("bytedance"))
    assert r.source == "mock"
    assert 0 <= r.score <= 5
    assert r.review_count > 0
    assert r.ceo_pct is not None
    assert "compensation" in r.breakdown


def test_get_company_reviews_unknown(provider):
    r = asyncio.run(provider.get_company_reviews("totally-unknown-co"))
    # 未知公司应返回兜底评分
    assert r.score > 0
    assert "compensation" in r.breakdown


def test_get_company_reviews_id_prefix(provider):
    """兼容 'kanzhun:bytedance' 形式 ID."""
    r = asyncio.run(provider.get_company_reviews("kanzhun:bytedance"))
    assert r.source == "mock"
    assert 3.0 <= r.score <= 5.0


def test_get_company_reviews_chinese_name(provider):
    """兼容中文名."""
    r = asyncio.run(provider.get_company_reviews("字节跳动"))
    assert r.source == "mock"
    assert 3.0 <= r.score <= 5.0


def test_get_employee_reviews_order(provider):
    reviews = asyncio.run(provider.get_employee_reviews("bytedance", page_size=5))
    assert len(reviews) <= 5
    # 按时间倒序
    if len(reviews) >= 2:
        assert (reviews[0].created_at or "") >= (reviews[1].created_at or "")


def test_get_employee_reviews_pagination(provider):
    p1 = asyncio.run(provider.get_employee_reviews("bytedance", page=1, page_size=3))
    p2 = asyncio.run(provider.get_employee_reviews("bytedance", page=2, page_size=3))
    if len(p1) == 3 and len(p2) > 0:
        ids1 = {r.id for r in p1}
        ids2 = {r.id for r in p2}
        assert ids1.isdisjoint(ids2)


def test_get_interview_experiences(provider):
    ints = asyncio.run(provider.get_interview_experiences("bytedance", page_size=5))
    assert len(ints) <= 5
    if ints:
        i = ints[0]
        assert 1 <= i.difficulty <= 5
        assert i.experience in ("positive", "neutral", "negative")
        assert i.result in ("offer", "rejected", "pending", "no_response")


def test_get_salary_insights(provider):
    s = asyncio.run(provider.get_salary_insights("bytedance"))
    assert s.currency == "CNY"
    assert s.median_k > 0
    assert s.p25_k is not None and s.p25_k <= s.median_k
    assert s.p75_k is not None and s.p75_k >= s.median_k
    assert "python" in s.by_role


def test_cache(provider):
    """二次调用应命中内存缓存."""
    import time

    r1 = asyncio.run(provider.get_company_reviews("bytedance"))
    # 立即再调
    r2 = asyncio.run(provider.get_company_reviews("bytedance"))
    assert r1.score == r2.score
    assert r1.review_count == r2.review_count