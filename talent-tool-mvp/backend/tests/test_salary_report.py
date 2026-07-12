"""Tests for Salary Report Service (T2402).

验证:
- 百分位计算正确性
- 趋势聚合
- offer 定位
"""
from __future__ import annotations

import pytest

from services.platform.salary_report import (
    SalaryReportService,
    get_salary_report_service,
)


@pytest.fixture
def svc():
    return SalaryReportService()


def test_distribution_basic(svc):
    d = svc.compute_salary_distribution("python", "北京", "mid")
    assert d.role == "python"
    assert d.city == "北京"
    assert d.seniority == "mid"
    # 分位单调递增
    assert d.p10_k <= d.p25_k <= d.p50_k <= d.p75_k <= d.p90_k
    assert d.sample_size > 0
    assert d.currency == "CNY"


def test_distribution_seniority_ordering(svc):
    """junior < mid < senior 薪资."""
    junior = svc.compute_salary_distribution("python", "上海", "junior")
    mid = svc.compute_salary_distribution("python", "上海", "mid")
    senior = svc.compute_salary_distribution("python", "上海", "senior")
    assert junior.p50_k < mid.p50_k < senior.p50_k


def test_distribution_city_factor(svc):
    """一线城市 > 二线."""
    tier1 = svc.compute_salary_distribution("python", "北京", "mid")
    tier2 = svc.compute_salary_distribution("python", "成都", "mid")
    assert tier1.p50_k > tier2.p50_k


def test_distribution_role_algorithm_higher_than_qa(svc):
    algo = svc.compute_salary_distribution("algorithm", "北京", "mid")
    qa = svc.compute_salary_distribution("qa", "北京", "mid")
    assert algo.p50_k > qa.p50_k


def test_distribution_to_dict(svc):
    d = svc.compute_salary_distribution("python", "上海", "senior")
    out = d.to_dict()
    assert "p50_k" in out
    assert "sample_size" in out
    assert out["currency"] == "CNY"


def test_trend_monthly(svc):
    t = svc.compute_trend_sync("python", "北京", period="monthly", months=12)
    assert t.period == "monthly"
    assert len(t.points) == 12
    for p in t.points:
        assert "period" in p
        assert "median_k" in p


def test_trend_quarterly(svc):
    t = svc.compute_trend_sync("python", "上海", period="quarterly", months=12)
    assert t.period == "quarterly"
    # 12 个月 跨 5 个季度 (含当前季度)
    assert 4 <= len(t.points) <= 5
    assert all("Q" in p["period"] for p in t.points)


def test_trend_yearly(svc):
    t = svc.compute_trend_sync("python", "深圳", period="yearly", months=24)
    assert t.period == "yearly"
    # 24 个月 跨 2-3 个年
    assert 2 <= len(t.points) <= 3


def test_trend_change_6m(svc):
    """6 个月变化率应在合理范围内."""
    t = svc.compute_trend_sync("python", "北京", period="monthly", months=12)
    assert isinstance(t.change_6m_pct, float)
    assert -50.0 <= t.change_6m_pct <= 50.0


def test_locate_offer_competitive(svc):
    """Offer 接近 P50 -> competitive."""
    dist = svc.compute_salary_distribution("python", "北京", "mid")
    pos = svc.locate_offer("python", "北京", "mid", dist.p50_k)
    assert pos.recommendation == "competitive"
    assert 45.0 <= pos.percentile_rank <= 55.0


def test_locate_offer_high(svc):
    """Offer > P90 -> high."""
    dist = svc.compute_salary_distribution("python", "北京", "mid")
    pos = svc.locate_offer("python", "北京", "mid", dist.p90_k * 1.5)
    assert pos.recommendation == "high"
    assert pos.percentile_rank >= 90.0


def test_locate_offer_low(svc):
    """Offer < P25 -> low."""
    dist = svc.compute_salary_distribution("python", "北京", "mid")
    pos = svc.locate_offer("python", "北京", "mid", dist.p10_k * 0.5)
    assert pos.recommendation == "low"
    assert pos.percentile_rank < 25.0


def test_locate_offer_to_dict(svc):
    dist = svc.compute_salary_distribution("python", "上海", "senior")
    pos = svc.locate_offer("python", "上海", "senior", dist.p75_k)
    out = pos.to_dict()
    assert "offer_k" in out
    assert "percentile_rank" in out
    assert "recommendation" in out


def test_cache(svc):
    """二次调用应命中缓存."""
    d1 = svc.compute_salary_distribution("python", "北京", "mid")
    d2 = svc.compute_salary_distribution("python", "北京", "mid")
    assert d1.p50_k == d2.p50_k


def test_get_salary_report_service_singleton():
    s1 = get_salary_report_service()
    s2 = get_salary_report_service()
    assert s1 is s2


def test_distribution_clear_cache(svc):
    svc.compute_salary_distribution("python", "北京", "mid")
    svc.clear_cache()
    assert svc._cache == {}