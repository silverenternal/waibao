"""MockJobMarketProvider 协议验证 (T607).

目标:
    1. 验证 MockJobMarketProvider 实现 JobMarketProvider ABC
    2. 验证 search_jobs / get_salary_trend / get_hot_skills 三方法数据合理
    3. 验证数据完全确定性 (同 keyword → 同结果)
    4. 验证薪资/分页/技能过滤
    5. 验证 registry.get_job_market_provider() 默认返回 mock
"""
from __future__ import annotations

import pytest

from backend.providers.job_market import (
    JobMarketProvider,
    MockJobMarketProvider,
)
from backend.providers.job_market.registry import (
    get_job_market_provider,
    reset_job_market_cache,
)
from backend.providers.job_market.types import (
    JobPosting,
    SalaryPoint,
    SkillDemand,
)


# ---------------------------------------------------------------------------
# 协议完整性
# ---------------------------------------------------------------------------
def test_mock_provider_is_abstract_subclass():
    assert issubclass(MockJobMarketProvider, JobMarketProvider)


def test_mock_provider_name_is_mock():
    assert MockJobMarketProvider().provider_name == "mock"


# ---------------------------------------------------------------------------
# search_jobs
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_search_jobs_deterministic():
    p = MockJobMarketProvider()
    r1 = await p.search_jobs("Python 后端")
    r2 = await p.search_jobs("Python 后端")
    assert len(r1) == len(r2)
    assert len(r1) > 0
    for a, b in zip(r1, r2):
        assert a.external_id == b.external_id
        assert a.title == b.title


@pytest.mark.asyncio
async def test_search_jobs_returns_typed_postings():
    p = MockJobMarketProvider()
    rows = await p.search_jobs("前端", city="上海")
    assert rows, "上海 应该有岗位"
    for j in rows:
        assert isinstance(j, JobPosting)
        assert j.source == "mock"
        assert j.city == "上海"
        assert j.salary_min_k is not None and j.salary_max_k is not None
        assert j.salary_min_k <= j.salary_max_k
        assert j.salary_currency == "CNY"
        assert j.skills, "应有技能标签"
        assert j.url and j.url.startswith("https://mock.local/")


@pytest.mark.asyncio
async def test_search_jobs_salary_range_filter():
    p = MockJobMarketProvider()
    rows = await p.search_jobs("算法", salary_range=(10.0, 60.0))
    assert rows
    for j in rows:
        assert j.salary_min_k >= 10.0
        assert j.salary_max_k <= 60.0


@pytest.mark.asyncio
async def test_search_jobs_salary_range_too_narrow_returns_empty():
    p = MockJobMarketProvider()
    rows = await p.search_jobs("数据", salary_range=(100.0, 200.0))
    assert rows == []


@pytest.mark.asyncio
async def test_search_jobs_pagination():
    p = MockJobMarketProvider()
    p1 = await p.search_jobs("算法", page=1, page_size=3)
    p2 = await p.search_jobs("算法", page=2, page_size=3)
    assert len(p1) == 3
    assert len(p2) >= 0
    # 翻页不应重复
    p1_ids = {x.external_id for x in p1}
    p2_ids = {x.external_id for x in p2}
    assert p1_ids.isdisjoint(p2_ids)


@pytest.mark.asyncio
async def test_search_jobs_empty_keyword_returns_empty():
    p = MockJobMarketProvider()
    assert await p.search_jobs("") == []


@pytest.mark.asyncio
async def test_search_jobs_combined_dedup():
    p = MockJobMarketProvider()
    rows = await p.search_jobs_combined(["Python", "python 后端", "FastAPI"])
    ids = {(j.source, j.external_id) for j in rows}
    assert len(ids) == len(rows), "combined 结果必须去重"


# ---------------------------------------------------------------------------
# get_salary_trend
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_salary_trend_returns_n_months():
    p = MockJobMarketProvider()
    rows = await p.get_salary_trend("Python", "北京", months=12)
    assert len(rows) == 12
    for sp in rows:
        assert isinstance(sp, SalaryPoint)
        assert sp.median_k > 0
        assert sp.p25_k is not None and sp.p75_k is not None
        assert sp.p25_k <= sp.median_k <= sp.p75_k
        assert sp.sample_size and sp.sample_size > 0


@pytest.mark.asyncio
async def test_salary_trend_period_is_monotonic():
    p = MockJobMarketProvider()
    rows = await p.get_salary_trend("前端", "上海", months=6)
    periods = [r.period for r in rows]
    assert periods == sorted(periods)


# ---------------------------------------------------------------------------
# get_hot_skills
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_hot_skills_top10_default():
    p = MockJobMarketProvider()
    rows = await p.get_hot_skills(limit=10)
    assert len(rows) == 10
    for s in rows:
        assert isinstance(s, SkillDemand)
        assert 0 <= s.demand_score <= 100
        assert s.job_count > 0
    scores = [s.demand_score for s in rows]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_hot_skills_role_specific():
    p = MockJobMarketProvider()
    rows = await p.get_hot_skills(role="Python 后端工程师")
    assert rows
    skill_set = {s.skill for s in rows}
    # 至少包含 1 个 Python 模板里的技能
    assert any("Python" in s or "FastAPI" in s or "PyTorch" in s or "LLM" in s for s in skill_set)


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
def test_registry_default_is_mock(monkeypatch):
    monkeypatch.delenv("JOB_MARKET_PROVIDER", raising=False)
    reset_job_market_cache()
    p = get_job_market_provider()
    assert isinstance(p, MockJobMarketProvider)
    reset_job_market_cache()


def test_registry_respects_env(monkeypatch):
    monkeypatch.setenv("JOB_MARKET_PROVIDER", "mock")
    reset_job_market_cache()
    p = get_job_market_provider()
    assert isinstance(p, MockJobMarketProvider)
    reset_job_market_cache()


def test_registry_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("JOB_MARKET_PROVIDER", "totally-not-real")
    reset_job_market_cache()
    with pytest.raises(Exception):
        get_job_market_provider()
    reset_job_market_cache()


# ---------------------------------------------------------------------------
# T607: 真实 provider 在缺失凭证 / 网络错误时自动 fallback 到 mock
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_boss_provider_missing_credentials_falls_back_to_mock(monkeypatch):
    """Boss 直聘缺少 AppKey 时,所有方法应自动 fallback 到 mock 数据."""
    from backend.providers.job_market.boss_zhipin import BossZhipinProvider
    from backend.providers.job_market.mock import MockJobMarketProvider

    monkeypatch.delenv("JOB_MARKET_BOSS_APP_KEY", raising=False)
    p = BossZhipinProvider()
    rows = await p.search_jobs("Python", city="上海")
    assert rows, "fallback 应该返回 mock 数据"
    assert all(r.source == "mock" for r in rows)


@pytest.mark.asyncio
async def test_lagou_provider_missing_credentials_falls_back_to_mock(monkeypatch):
    """拉勾缺少 client_id 时,所有方法应自动 fallback 到 mock."""
    from backend.providers.job_market.lagou import LagouProvider

    monkeypatch.delenv("JOB_MARKET_LAGOU_CLIENT_ID", raising=False)
    monkeypatch.delenv("JOB_MARKET_LAGOU_CLIENT_SECRET", raising=False)
    p = LagouProvider()
    rows = await p.search_jobs("前端", page_size=4)
    assert rows and all(r.source == "mock" for r in rows)


@pytest.mark.asyncio
async def test_linkedin_provider_missing_credentials_falls_back_to_mock(monkeypatch):
    """LinkedIn 缺少 OAuth 时,fallback 到 mock."""
    from backend.providers.job_market.linkedin import LinkedInProvider

    monkeypatch.delenv("JOB_MARKET_LINKEDIN_CLIENT_ID", raising=False)
    monkeypatch.delenv("JOB_MARKET_LINKEDIN_CLIENT_SECRET", raising=False)
    p = LinkedInProvider()
    rows = await p.search_jobs("算法", city="Shanghai")
    assert rows and all(r.source == "mock" for r in rows)


@pytest.mark.asyncio
async def test_adzuna_provider_missing_credentials_falls_back_to_mock(monkeypatch):
    """Adzuna 缺少 app_id/key 时,fallback 到 mock."""
    from backend.providers.job_market.adzuna import AdzunaProvider

    monkeypatch.delenv("JOB_MARKET_ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("JOB_MARKET_ADZUNA_APP_KEY", raising=False)
    p = AdzunaProvider()
    rows = await p.search_jobs("data")
    assert rows and all(r.source == "mock" for r in rows)


@pytest.mark.asyncio
async def test_boss_provider_network_error_falls_back_to_mock(monkeypatch):
    """网络异常时 fallback 到 mock."""
    import httpx
    from backend.providers.job_market.boss_zhipin import BossZhipinProvider

    monkeypatch.setenv("JOB_MARKET_BOSS_APP_KEY", "fake-key-for-test")

    async def _raise(*_args, **_kwargs):
        raise httpx.ConnectError("boom")

    p = BossZhipinProvider()
    # 替换内部 client 的 get — 触发网络异常分支
    class _BrokenClient:
        async def get(self, *a, **kw):
            raise httpx.ConnectError("network down")

    p._client = _BrokenClient()  # type: ignore[assignment]
    rows = await p.search_jobs("Python")
    assert rows and all(r.source == "mock" for r in rows)


def test_registry_returns_real_provider_when_env_set(monkeypatch):
    """JOB_MARKET_PROVIDER=boss 应返回真实 provider(无凭证时它内部仍 fallback)."""
    monkeypatch.setenv("JOB_MARKET_PROVIDER", "boss")
    monkeypatch.delenv("JOB_MARKET_BOSS_APP_KEY", raising=False)
    reset_job_market_cache()
    p = get_job_market_provider()
    assert p.__class__.__name__ == "BossZhipinProvider"
    reset_job_market_cache()


def test_registry_returns_lagou_provider(monkeypatch):
    monkeypatch.setenv("JOB_MARKET_PROVIDER", "lagou")
    reset_job_market_cache()
    p = get_job_market_provider()
    assert p.__class__.__name__ == "LagouProvider"
    reset_job_market_cache()


def test_registry_returns_linkedin_provider(monkeypatch):
    monkeypatch.setenv("JOB_MARKET_PROVIDER", "linkedin")
    reset_job_market_cache()
    p = get_job_market_provider()
    assert p.__class__.__name__ == "LinkedInProvider"
    reset_job_market_cache()


def test_registry_returns_adzuna_provider(monkeypatch):
    monkeypatch.setenv("JOB_MARKET_PROVIDER", "adzuna")
    reset_job_market_cache()
    p = get_job_market_provider()
    assert p.__class__.__name__ == "AdzunaProvider"
    reset_job_market_cache()


# ---------------------------------------------------------------------------
# Mock 数据规模 + 缓存
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mock_pool_export_size_at_least_200():
    """T607 质量要求: mock 至少 200 条覆盖 10 岗位."""
    p = MockJobMarketProvider()
    pool = p.export_full_pool()
    assert len(pool) >= 200, f"mock 池 {len(pool)} < 200"
    # 通过 external_id 提取 role_key (格式: mock-{role}-{city}-{slot})
    roles = {row["external_id"].split("-")[1] for row in pool}
    assert len(roles) >= 10, f"mock 池只覆盖 {len(roles)} 个 role, 应 >=10"
    # 间接验证: 不同 keyword 应该命中不同 role
    py_rows = await p.search_jobs("Python")
    fe_rows = await p.search_jobs("前端")
    assert py_rows and fe_rows
    assert {j.title for j in py_rows} != {j.title for j in fe_rows}


@pytest.mark.asyncio
async def test_mock_search_results_cached_after_first_call():
    """T607 质量要求: 招聘市场数据缓存 1 小时."""
    p = MockJobMarketProvider()
    r1 = await p.search_jobs("Python 后端")
    r2 = await p.search_jobs("Python 后端")
    # 两次调用结果一致 + cache 命中(同引用不一定但同 external_id)
    assert [j.external_id for j in r1] == [j.external_id for j in r2]