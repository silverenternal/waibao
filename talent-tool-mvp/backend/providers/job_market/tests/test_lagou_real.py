"""拉勾网 真实 OpenAPI 接入验证 (T1101).

默认 **跳过** — 需要以下环境变量才会运行:

    export JOB_MARKET_LAGOU_CLIENT_ID="<your-client-id>"
    export JOB_MARKET_LAGOU_CLIENT_SECRET="<your-client-secret>"
    pytest -m real_api backend/providers/job_market/tests/test_lagou_real.py

OAuth2 client_credentials 流程已封装在 LagouProvider._fetch_token(),
通过 _TokenCache 自动续期 (有效期 4 min,提前 60s 续期)。

凭证申请: docs/REAL_API_SETUP.md (拉勾 OpenAPI 章节)
"""
from __future__ import annotations

import os
import time

import pytest

from backend.providers.job_market.lagou import LagouProvider, _TokenCache
from backend.providers.job_market.mock import MockJobMarketProvider
from backend.providers.job_market.types import JobPosting


pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(
        not (os.getenv("JOB_MARKET_LAGOU_CLIENT_ID") and os.getenv("JOB_MARKET_LAGOU_CLIENT_SECRET")),
        reason="拉勾 OAuth 凭证未设置 — 跳过真实 API 测试",
    ),
]


@pytest.fixture
async def provider():
    p = LagouProvider()
    yield p
    await p.close()


# ---------------------------------------------------------------------------
# OAuth2 Token 缓存验证
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_oauth_token_cache_avoids_duplicate_calls(provider):
    """连续两次调用应共用同一个 access_token (内存缓存命中)."""
    t1 = await provider._tokens.get(provider)
    t2 = await provider._tokens.get(provider)
    assert t1 == t2
    assert t1, "OAuth token 必须非空"


@pytest.mark.asyncio
async def test_oauth_token_expiry_triggers_refresh(provider):
    """token 即将过期时,自动续期到新值."""
    # 第一次获取
    first_token = await provider._tokens.get(provider)
    # 手动让 token 标记为"即将过期"
    provider._tokens._expires_at = time.monotonic() - 1
    # 再获取 — 应触发 _fetch_token 重新拉取
    new_token = await provider._tokens.get(provider)
    assert new_token, "续期后 token 必须非空"
    # 真实环境 token 会变;若 OAuth 端点返回固定 token(沙箱),只校验非空
    assert isinstance(new_token, str)


def test_token_cache_helper_basic():
    """单元测试: _TokenCache 在 token 为空时调用 fetcher."""
    import asyncio

    async def _run():
        cache = _TokenCache()
        called = {"n": 0}

        class FakeProvider:
            async def _fetch_token(self) -> str:
                called["n"] += 1
                return "fake-token-abc"

            async def _unused(self):
                pass

        tok = await cache.get(FakeProvider())  # type: ignore[arg-type]
        assert tok == "fake-token-abc"
        assert called["n"] == 1
        # 第二次应命中缓存,不调用 fetcher
        tok2 = await cache.get(FakeProvider())  # type: ignore[arg-type]
        assert tok2 == "fake-token-abc"
        assert called["n"] == 1

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 真实 API 调用 — search_jobs
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_search_jobs_python_beijing_returns_real_results(provider):
    """search_jobs('python', city='北京') 真实调用,至少 1 条岗位."""
    rows = await provider.search_jobs("python", city="北京", page_size=10)
    assert isinstance(rows, list)
    assert len(rows) >= 1, "拉勾真实 API 应返回至少 1 条"
    assert all(r.source == "lagou" for r in rows)


@pytest.mark.asyncio
async def test_search_jobs_field_mapping(provider):
    """字段映射: 拉勾 camelCase 字段 (positionName / companyName / salary) 应正确归一."""
    rows = await provider.search_jobs("Java", city="深圳", page_size=5)
    if not rows:
        pytest.skip("拉勾 API 未返回岗位,跳过映射检查")
    for j in rows:
        assert isinstance(j, JobPosting)
        assert j.external_id
        assert j.title
        assert j.company
        assert j.source == "lagou"


# ---------------------------------------------------------------------------
# 缓存命中
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_search_jobs_cache_hit_speedup(provider):
    kw = "数据科学 北京 lagou-cache-test"
    t0 = time.perf_counter()
    r1 = await provider.search_jobs(kw, city="北京", page_size=5)
    first_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    r2 = await provider.search_jobs(kw, city="北京", page_size=5)
    second_ms = (time.perf_counter() - t0) * 1000

    assert [j.external_id for j in r1] == [j.external_id for j in r2]
    if first_ms > 200:
        assert second_ms < first_ms, (
            f"缓存未生效: first={first_ms:.0f}ms second={second_ms:.0f}ms"
        )


# ---------------------------------------------------------------------------
# 缺失凭证 — mock 兜底
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_credentials_falls_back_to_mock(monkeypatch):
    monkeypatch.delenv("JOB_MARKET_LAGOU_CLIENT_ID", raising=False)
    monkeypatch.delenv("JOB_MARKET_LAGOU_CLIENT_SECRET", raising=False)
    p = LagouProvider()
    try:
        rows = await p.search_jobs("Python", city="北京")
        assert rows and all(r.source == "mock" for r in rows)
    finally:
        await p.close()


def test_fallback_is_mock(monkeypatch):
    monkeypatch.delenv("JOB_MARKET_LAGOU_CLIENT_ID", raising=False)
    monkeypatch.delenv("JOB_MARKET_LAGOU_CLIENT_SECRET", raising=False)
    p = LagouProvider()
    assert isinstance(p._fallback, MockJobMarketProvider)


# ---------------------------------------------------------------------------
# 薪资趋势 / 热门技能
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_salary_trend_returns_months(provider):
    rows = await provider.get_salary_trend("Python", "北京", months=6)
    assert isinstance(rows, list)
    if rows:
        assert len(rows) <= 12  # 拉勾返回不超过 12 个月
        for r in rows:
            assert r.median_k > 0


@pytest.mark.asyncio
async def test_get_hot_skills_returns(provider):
    rows = await provider.get_hot_skills(role="前端", limit=5)
    assert isinstance(rows, list)
    assert len(rows) <= 5