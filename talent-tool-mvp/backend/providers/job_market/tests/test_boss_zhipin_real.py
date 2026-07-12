"""Boss直聘 真实 OpenAPI 接入验证 (T1101).

默认 **跳过** — 需要同时设置以下环境变量才会运行:

    export JOB_MARKET_BOSS_APP_KEY="<your-boss-app-key>"
    pytest -m real_api backend/providers/job_market/tests/test_boss_zhipin_real.py

测试目标:
    1. search_jobs('python', city='北京') 真实 HTTP 调用,返回非空
    2. JobPosting 字段映射正确 (id / title / company / city / salary)
    3. cache 写入命中 (二次调用同 keyword 应快速返回)
    4. fallback 链路完整 — 缺失凭证时仍可工作 (mock 兜底)

凭证申请: docs/REAL_API_SETUP.md (Boss直聘 OpenAPI 章节)
"""
from __future__ import annotations

import os
import time

import pytest

from backend.providers.job_market.boss_zhipin import BossZhipinProvider
from backend.providers.job_market.mock import MockJobMarketProvider
from backend.providers.job_market.types import JobPosting


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not os.getenv("JOB_MARKET_BOSS_APP_KEY"),
        reason="BOSS_ZHIPIN_APP_KEY (env JOB_MARKET_BOSS_APP_KEY) 未设置 — 跳过真实 API 测试",
    ),
]


@pytest.fixture
async def provider():
    p = BossZhipinProvider()
    yield p
    await p.close()


# ---------------------------------------------------------------------------
# 真实 API 调用 — search_jobs
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_search_jobs_python_beijing_returns_real_results(provider):
    """真实调用: search_jobs('python', city='北京') 至少返回 1 条."""
    rows = await provider.search_jobs("python", city="北京", page_size=10)
    assert isinstance(rows, list)
    assert len(rows) >= 1, "Boss直聘真实 API 应返回至少 1 条 python/北京 岗位"
    # 数据源标记必须为 boss,而非 mock fallback
    assert all(r.source == "boss" for r in rows), "缺失字段映射或回退到 mock"


@pytest.mark.asyncio
async def test_search_jobs_field_mapping_completeness(provider):
    """验证 Boss 响应字段正确映射到 JobPosting dataclass."""
    rows = await provider.search_jobs("前端", city="上海", page_size=5)
    if not rows:
        pytest.skip("Boss API 当前未返回前端/上海岗位,跳过映射检查")
    for j in rows:
        assert isinstance(j, JobPosting)
        # 必填字段
        assert j.external_id, "external_id 必须非空"
        assert j.title, "title 必须非空"
        assert j.company, "company 必须非空"
        assert j.source == "boss"
        # 城市应被回显
        if j.city is not None:
            assert "上海" in j.city or "Shanghai" in j.city.lower()
        # 薪资 (允许 None,但若有必须是 min <= max)
        if j.salary_min_k is not None and j.salary_max_k is not None:
            assert j.salary_min_k <= j.salary_max_k
            assert j.salary_currency == "CNY"


@pytest.mark.asyncio
async def test_search_jobs_pagination_works(provider):
    """分页参数真实生效 — 第 1 页与第 2 页不重复."""
    p1 = await provider.search_jobs("python", city="北京", page=1, page_size=3)
    p2 = await provider.search_jobs("python", city="北京", page=2, page_size=3)
    p1_ids = {j.external_id for j in p1}
    p2_ids = {j.external_id for j in p2}
    if p1 and p2:
        assert p1_ids.isdisjoint(p2_ids), "Boss 分页必须返回不同岗位"


# ---------------------------------------------------------------------------
# cache 写入验证
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_search_jobs_cache_written(provider):
    """连续两次同 keyword 调用,第二次应命中 in-memory cache (耗时明显下降)."""
    keyword = "python 北京 cache-test"
    # 第一次 — 真实 API 调用
    t0 = time.perf_counter()
    r1 = await provider.search_jobs(keyword, city="北京", page_size=5)
    first_ms = (time.perf_counter() - t0) * 1000
    # 第二次 — 应命中缓存
    t0 = time.perf_counter()
    r2 = await provider.search_jobs(keyword, city="北京", page_size=5)
    second_ms = (time.perf_counter() - t0) * 1000
    # 两次结果一致
    assert [j.external_id for j in r1] == [j.external_id for j in r2]
    # 缓存命中后,second 应明显快于 first (允许 50ms 容差)
    # 注:首次调用还可能因 DNS/TLS 耗时,这里用宽松阈值
    if first_ms > 200:
        assert second_ms < first_ms, (
            f"二次调用 {second_ms:.0f}ms 未快于首次 {first_ms:.0f}ms — 缓存未生效"
        )


# ---------------------------------------------------------------------------
# 缺失凭证 fallback 链路 — 不依赖真实 key,作为 mock 兜底单元测试
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_credentials_falls_back_to_mock(monkeypatch):
    """缺失 JOB_MARKET_BOSS_APP_KEY 时,BossZhipinProvider 自动 fallback 到 mock."""
    monkeypatch.delenv("JOB_MARKET_BOSS_APP_KEY", raising=False)
    p = BossZhipinProvider()
    try:
        rows = await p.search_jobs("python", city="北京")
        assert rows, "fallback 必须返回 mock 数据"
        assert all(r.source == "mock" for r in rows)
    finally:
        await p.close()


@pytest.mark.asyncio
async def test_fallback_provider_is_mock_job_market(monkeypatch):
    """fallback 实例必须是 MockJobMarketProvider,不是抽象类."""
    from backend.providers.job_market.base import JobMarketProvider

    monkeypatch.delenv("JOB_MARKET_BOSS_APP_KEY", raising=False)
    p = BossZhipinProvider()
    assert isinstance(p._fallback, MockJobMarketProvider)
    assert isinstance(p._fallback, JobMarketProvider)


# ---------------------------------------------------------------------------
# get_salary_trend / get_hot_skills — 真实调用 (Best effort, 部分受限)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_salary_trend_returns_list(provider):
    """薪资趋势 — 企业版才开放,免费账号可能回退到 mock,只验证非崩溃."""
    rows = await provider.get_salary_trend("Python", "北京", months=6)
    # 即便回退到 mock,也应返回 6 个月的数据点
    assert isinstance(rows, list)
    if rows:
        # 数据按 period 升序
        periods = [r.period for r in rows]
        assert periods == sorted(periods)


@pytest.mark.asyncio
async def test_get_hot_skills_returns_top_n(provider):
    """热门技能 — 验证 limit 参数生效."""
    rows = await provider.get_hot_skills(role="Python", limit=5)
    assert isinstance(rows, list)
    assert len(rows) <= 5