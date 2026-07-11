"""learning_resources 服务测试 (T607)."""
from __future__ import annotations

import pytest

from backend.services.learning_resources import (
    LearningResourcesService,
    _fallback_for_skill,
    reset_learning_resources_cache,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_learning_resources_cache()
    yield
    reset_learning_resources_cache()


# ---------------------------------------------------------------------------
# 基本结构
# ---------------------------------------------------------------------------
def test_service_singleton():
    from backend.services.learning_resources import get_learning_resources_service

    a = get_learning_resources_service()
    b = get_learning_resources_service()
    assert a is b


def test_fallback_pool_not_empty():
    rows = _fallback_for_skill("Python")
    assert rows, "fallback 池应该有数据"
    for r in rows:
        assert r.title
        assert r.url
        assert r.provider in {"coursera", "geekbang", "juejin", "imooc", "bilibili"}


def test_fallback_returns_at_least_5_items():
    rows = _fallback_for_skill("完全不存在的技能 xxx")
    assert len(rows) >= 5


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_search_returns_resources():
    svc = LearningResourcesService()
    # 注入 mock provider 模式: 直接调 search,所有真实 provider 会失败 → fallback
    rows = await svc.search("Python", limit=10)
    # 即使所有上游失败,fallback 必须有数据,不会阻塞业务
    assert rows, "search 永远不能返回空(失败时走 fallback)"
    assert len(rows) <= 10


@pytest.mark.asyncio
async def test_search_caches_results():
    svc = LearningResourcesService()
    r1 = await svc.search("FastAPI", limit=5)
    r2 = await svc.search("FastAPI", limit=5)
    # 缓存命中 → 列表内容一致
    assert [(x.title, x.provider) for x in r1] == [(x.title, x.provider) for x in r2]


@pytest.mark.asyncio
async def test_search_empty_skill_returns_empty():
    svc = LearningResourcesService()
    assert await svc.search("") == []
    assert await svc.search("   ") == []


@pytest.mark.asyncio
async def test_search_dedups_across_providers():
    svc = LearningResourcesService()
    rows = await svc.search("Kubernetes", limit=20)
    keys = [f"{r.provider}::{r.title.lower()}" for r in rows]
    assert len(keys) == len(set(keys)), "search 结果必须去重"


# ---------------------------------------------------------------------------
# recommend()
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recommend_combines_gap_skills():
    svc = LearningResourcesService()
    rows = await svc.recommend(["Python", "FastAPI", "Kubernetes"])
    assert rows, "recommend 必须有结果"
    # 综合评分应大于 0
    for r in rows:
        assert r.rating >= 0


@pytest.mark.asyncio
async def test_recommend_empty_skills_returns_empty():
    svc = LearningResourcesService()
    assert await svc.recommend([]) == []


@pytest.mark.asyncio
async def test_recommend_respects_overall_limit():
    svc = LearningResourcesService()
    rows = await svc.recommend(
        ["Python", "FastAPI", "Rust", "Kubernetes", "PostgreSQL"],
        overall_limit=8,
    )
    assert len(rows) <= 8


@pytest.mark.asyncio
async def test_recommend_skill_tags_include_input():
    svc = LearningResourcesService()
    rows = await svc.recommend(["Rust"])
    if rows:
        # 至少有一条的 skill_tags 包含 rust (大小写不敏感)
        assert any("rust" in (t.lower()) for r in rows for t in r.skill_tags)


# ---------------------------------------------------------------------------
# 缓存 TTL
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cache_ttl_7_days(monkeypatch):
    svc = LearningResourcesService()
    # 把 cache TTL 调成很小,验证过期清除
    import time
    svc._cache["search::python::20"] = (time.monotonic() - 1e9, [])
    rows = await svc.search("Python")
    # 缓存项已过期 → 重新查询,应该返回非空 fallback
    assert rows