"""T1702 — NPS + LLM 分类单测."""
from __future__ import annotations

import os
import sys
import types
from unittest.mock import patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# calculate_nps
# ---------------------------------------------------------------------------


def test_calculate_nps_classic():
    from services.integrations.nps_service import calculate_nps

    res = calculate_nps([10, 9, 9, 8, 7, 6, 0])
    # 3 promoter (10,9,9) + 2 passive (8,7) + 2 detractor (6,0) = 7
    assert res.promoters == 3
    assert res.passives == 2
    assert res.detractors == 2
    assert res.responses == 7
    # (3-2)/7 = 14.2857 → 14.3
    assert res.nps == 14.3
    assert res.meets_target is False  # target=40, nps=14.3


def test_calculate_nps_meets_target():
    from services.integrations.nps_service import calculate_nps

    res = calculate_nps([10, 10, 10, 9, 8])
    # 4 promoter, 1 passive, 0 detractor → 80.0
    assert res.nps == 80.0
    assert res.meets_target is True


def test_calculate_nps_target_override():
    from services.integrations.nps_service import calculate_nps

    res = calculate_nps([10, 10, 9, 9], target=70)
    # 4 promoter / 4 = 100
    assert res.nps == 100.0
    assert res.target == 70
    assert res.meets_target is True


def test_calculate_nps_empty():
    from services.integrations.nps_service import calculate_nps

    res = calculate_nps([])
    assert res.nps is None
    assert res.meets_target is False
    assert res.responses == 0


def test_calculate_nps_ignores_none():
    from services.integrations.nps_service import calculate_nps

    res = calculate_nps([None, 10, 9, None, 0])
    assert res.responses == 3
    assert res.promoters == 2
    assert res.detractors == 1


# ---------------------------------------------------------------------------
# categorize_feedback — heuristic fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_categorize_feedback_bug_keyword():
    from services.integrations.nps_service import categorize_feedback

    res = await categorize_feedback("页面崩溃了,点提交就报错 500", use_llm=False)
    assert res.category == "bug"
    assert res.sentiment == "negative"


@pytest.mark.asyncio
async def test_categorize_feedback_feature_keyword():
    from services.integrations.nps_service import categorize_feedback

    res = await categorize_feedback("希望能支持一键导出 CSV,目前缺少这个功能", use_llm=False)
    assert res.category == "feature_request"


@pytest.mark.asyncio
async def test_categorize_feedback_praise():
    from services.integrations.nps_service import categorize_feedback

    res = await categorize_feedback("非常好用,界面超棒,很喜欢", use_llm=False)
    assert res.category == "praise"
    assert res.sentiment == "positive"


@pytest.mark.asyncio
async def test_categorize_feedback_pricing():
    from services.integrations.nps_service import categorize_feedback

    res = await categorize_feedback("价格太贵了,套餐不划算", use_llm=False)
    assert res.category == "pricing"


@pytest.mark.asyncio
async def test_categorize_feedback_perf():
    from services.integrations.nps_service import categorize_feedback

    res = await categorize_feedback("加载太慢了,卡顿严重,性能需要优化", use_llm=False)
    assert res.category == "performance"


@pytest.mark.asyncio
async def test_categorize_feedback_docs():
    from services.integrations.nps_service import categorize_feedback

    res = await categorize_feedback("文档说明不够清楚,教程找不到", use_llm=False)
    assert res.category == "docs"


@pytest.mark.asyncio
async def test_categorize_feedback_empty():
    from services.integrations.nps_service import categorize_feedback

    res = await categorize_feedback("", use_llm=False)
    assert res.category == "other"
    assert res.confidence == 0.0


@pytest.mark.asyncio
async def test_categorize_feedback_no_match():
    from services.integrations.nps_service import categorize_feedback

    res = await categorize_feedback("今天天气真好", use_llm=False)
    assert res.category == "other"
    assert res.sentiment == "neutral"


# ---------------------------------------------------------------------------
# categorize_feedback — LLM path (mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_categorize_feedback_with_llm(monkeypatch):
    """Mock generate_text_cached 返回 JSON, 验证 LLM 路径解析正确."""

    async def _gen(*, prompt, model, temperature, max_tokens):
        return '{"category":"bug","confidence":0.92,"sentiment":"negative","tags":["login","crash"],"rationale":"login fails with 500"}'

    # Inject a fake module on the import path the service uses
    fake_mod = types.SimpleNamespace(generate_text_cached=_gen)
    monkeypatch.setitem(sys.modules, "services.llm_cache", fake_mod)

    from services.integrations import nps_service

    res = await nps_service.categorize_feedback("登录后报错,无法进入系统", use_llm=True)
    assert res.category == "bug"
    assert res.sentiment == "negative"
    assert res.confidence == 0.92
    assert "login" in res.tags


@pytest.mark.asyncio
async def test_categorize_feedback_llm_returns_garbage(monkeypatch):
    """LLM 返回非 JSON 时, 应回退到启发式."""

    async def _gen(*, prompt, model, temperature, max_tokens):
        return "I cannot categorize this."

    monkeypatch.setitem(sys.modules, "services.llm_cache", types.SimpleNamespace(generate_text_cached=_gen))

    from services.integrations import nps_service

    res = await nps_service.categorize_feedback("页面崩溃,无法操作", use_llm=True)
    # 回退到启发式
    assert res.category in {"bug", "other"}


@pytest.mark.asyncio
async def test_categorize_feedback_llm_module_missing(monkeypatch):
    """没有 LLM 模块时, 走启发式."""
    # 不要 import services.llm_cache, 让 import 失败
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "services.llm_cache" or name.endswith(".llm_cache"):
            raise ImportError("no llm cache")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    from services.integrations.nps_service import categorize_feedback

    res = await categorize_feedback("应用崩溃,bug 太多", use_llm=True)
    assert res.category in {"bug", "other"}


# ---------------------------------------------------------------------------
# categorize_many
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_categorize_many_returns_list():
    from services.integrations.nps_service import categorize_many

    res = await categorize_many(
        ["页面崩溃", "界面超棒", "价格太贵"],
        use_llm=False,
    )
    assert len(res) == 3
    assert res[0].category == "bug"
    assert res[1].category == "praise"
    assert res[2].category == "pricing"


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------


def test_nps_result_to_dict():
    from services.integrations.nps_service import calculate_nps, NPSResult

    r = calculate_nps([10, 9])
    d = r.to_dict()
    assert "nps" in d
    assert "promoters" in d
    assert "meets_target" in d


def test_categorized_feedback_to_dict():
    from services.integrations.nps_service import categorize_feedback, CategorizedFeedback
    import asyncio

    res = asyncio.run(categorize_feedback("test", use_llm=False))
    d = res.to_dict()
    assert "category" in d
    assert "tags" in d