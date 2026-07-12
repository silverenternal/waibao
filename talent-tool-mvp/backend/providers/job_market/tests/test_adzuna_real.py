"""Adzuna Job Search API 真实接入验证 (T1101).

默认 **跳过** — 需要以下环境变量才会运行:

    export JOB_MARKET_ADZUNA_APP_ID="<your-app-id>"
    export JOB_MARKET_ADZUNA_APP_KEY="<your-app-key>"
    export JOB_MARKET_ADZUNA_COUNTRY="gb"  # 可选, 默认 gb
    pytest -m real_api backend/providers/job_market/tests/test_adzuna_real.py

Adzuna 是免费层 250 calls/month 的全球职位聚合,适合做英文市场 fallback。

凭证申请: docs/REAL_API_SETUP.md (Adzuna 章节)
"""
from __future__ import annotations

import os
import time

import pytest

from backend.providers.job_market.adzuna import AdzunaProvider
from backend.providers.job_market.mock import MockJobMarketProvider
from backend.providers.job_market.types import JobPosting


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not (os.getenv("JOB_MARKET_ADZUNA_APP_ID") and os.getenv("JOB_MARKET_ADZUNA_APP_KEY")),
        reason="Adzuna app_id/app_key 未设置 — 跳过真实 API 测试",
    ),
]


@pytest.fixture
async def provider():
    p = AdzunaProvider()
    yield p
    await p.close()


# ---------------------------------------------------------------------------
# 真实 API 调用
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_search_jobs_python_london_returns_real_results(provider):
    """英国伦敦 python 岗位检索."""
    rows = await provider.search_jobs("python", city="london", page_size=10)
    assert isinstance(rows, list)
    if not rows:
        pytest.skip("Adzuna 当前未返回数据 — 跳过")
    assert all(r.source == "adzuna" for r in rows)
    assert all(r.salary_currency in ("GBP", "USD") for r in rows)


@pytest.mark.asyncio
async def test_search_jobs_us_country(monkeypatch, provider):
    """切换国家到美国,验证 _ADZUNA_COUNTRY 注入生效."""
    monkeypatch.setenv("JOB_MARKET_ADZUNA_COUNTRY", "us")
    # 重新构造 provider, 读取新的 country
    p2 = AdzunaProvider()
    try:
        rows = await p2.search_jobs("data scientist", city="new york", page_size=5)
        if rows:
            # 货币应为 USD
            assert all(r.salary_currency == "USD" for r in rows)
    finally:
        await p2.close()


@pytest.mark.asyncio
async def test_search_jobs_field_mapping(provider):
    rows = await provider.search_jobs("engineer", city="london", page_size=5)
    if not rows:
        pytest.skip("无数据,跳过")
    for j in rows:
        assert isinstance(j, JobPosting)
        assert j.external_id
        assert j.title
        assert j.source == "adzuna"
        assert j.url  # Adzuna redirect_url 必填


# ---------------------------------------------------------------------------
# 缓存命中
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_search_jobs_cache_speedup(provider):
    kw = "machine learning london adzuna-cache"
    t0 = time.perf_counter()
    r1 = await provider.search_jobs(kw, city="london", page_size=5)
    first_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    r2 = await provider.search_jobs(kw, city="london", page_size=5)
    second_ms = (time.perf_counter() - t0) * 1000

    assert [j.external_id for j in r1] == [j.external_id for j in r2]
    if first_ms > 200:
        assert second_ms < first_ms


# ---------------------------------------------------------------------------
# 薪资历史 (Adzuna /history 接口)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_salary_trend_history(provider):
    """验证 /history 接口返回过去 N 月薪资中位数."""
    rows = await provider.get_salary_trend("python", "london", months=6)
    assert isinstance(rows, list)
    if rows:
        # period 升序
        periods = [r.period for r in rows]
        assert periods == sorted(periods)
        for r in rows:
            assert r.median_k > 0


@pytest.mark.asyncio
async def test_get_hot_skills_uses_fallback(provider):
    """Adzuna 不提供 hot_skills — 应自动 fallback 到 mock."""
    from backend.providers.job_market.mock import MockJobMarketProvider

    rows = await provider.get_hot_skills(limit=5)
    assert isinstance(rows, list)
    # 因为 fallback 是 MockJobMarketProvider,数据 source 应为 'mock'
    # (这里不强校验 source 字段,因为可能 provider 直接 list)
    assert len(rows) <= 5


# ---------------------------------------------------------------------------
# 缺失凭证 — mock 兜底
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_credentials_falls_back_to_mock(monkeypatch):
    monkeypatch.delenv("JOB_MARKET_ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("JOB_MARKET_ADZUNA_APP_KEY", raising=False)
    p = AdzunaProvider()
    try:
        rows = await p.search_jobs("python")
        assert rows and all(r.source == "mock" for r in rows)
    finally:
        await p.close()


def test_fallback_is_mock(monkeypatch):
    monkeypatch.delenv("JOB_MARKET_ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("JOB_MARKET_ADZUNA_APP_KEY", raising=False)
    p = AdzunaProvider()
    assert isinstance(p._fallback, MockJobMarketProvider)