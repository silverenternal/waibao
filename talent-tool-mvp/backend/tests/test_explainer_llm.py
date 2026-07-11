"""T901 — explainer_llm 单元测试."""
from __future__ import annotations

import pytest

from matching.explainer_llm import (
    LLMExplainer,
    MockLLMProvider,
    Explanation,
    MatchScore,
    CandidateBrief,
    RoleBrief,
    _mock_generate_explain,
)


# ---------------------------------------------------------------------------
# MockLLMProvider 直接测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_provider_returns_full_schema():
    provider = MockLLMProvider()
    user_prompt = (
        "Role Title: Senior Backend Engineer\n"
        "Candidate Title: Backend Developer\n"
        "Experience Years: 6\n"
        "Skills Matched: Python, FastAPI, PostgreSQL\n"
        "Skills Partial: Docker\n"
        "Skills Missing: Kubernetes\n"
    )
    result = await provider.chat_json(system="x", user=user_prompt)
    assert "reasons" in result
    assert "weak_points" in result
    assert "counterfactual" in result
    assert isinstance(result["reasons"], list)
    assert isinstance(result["weak_points"], list)
    assert isinstance(result["counterfactual"], dict)
    assert "if_have" in result["counterfactual"]
    assert "score_lift" in result["counterfactual"]


@pytest.mark.asyncio
async def test_mock_provider_generates_counterfactual_from_missing_skill():
    provider = MockLLMProvider()
    user_prompt = "Skills Missing: Kubernetes, Helm"
    result = await provider.chat_json(system="x", user=user_prompt)
    cf = result["counterfactual"]
    assert "Kubernetes" in cf["if_have"]
    assert cf["score_lift"] > 0


@pytest.mark.asyncio
async def test_mock_provider_no_skills_still_returns():
    provider = MockLLMProvider()
    result = await provider.chat_json(system="x", user="empty")
    assert len(result["reasons"]) >= 1
    assert isinstance(result["counterfactual"]["score_lift"], float)


# ---------------------------------------------------------------------------
# LLMExplainer 端到端(用 mock provider)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explainer_with_mock_provider():
    explainer = LLMExplainer(provider=MockLLMProvider())
    score = MatchScore(
        overall=0.78,
        skill=0.85,
        semantic=0.72,
        experience=0.80,
        confidence="strong",
        skills_matched=["Python", "FastAPI"],
        skills_missing=["Kubernetes"],
    )
    cand = CandidateBrief(title="Backend Dev", seniority="Senior", years=6.0)
    role = RoleBrief(
        title="Senior Backend Engineer",
        seniority="Senior",
        required_skills=["Python", "FastAPI", "Kubernetes"],
        team_size=8,
    )
    explanation = await explainer.generate_explain(score, cand, role)
    assert isinstance(explanation, Explanation)
    assert len(explanation.reasons) > 0
    assert len(explanation.weak_points) > 0
    assert explanation.counterfactual["if_have"]
    assert 0.0 <= explanation.counterfactual["score_lift"] <= 0.5


@pytest.mark.asyncio
async def test_explainer_accepts_dict_inputs():
    explainer = LLMExplainer(provider=MockLLMProvider())
    explanation = await explainer.generate_explain(
        {"overall": 0.6, "skill": 0.6, "skills_matched": ["Python"]},
        {"title": "Dev", "years": 3},
        {"title": "Role", "required_skills": ["Python"]},
    )
    assert explanation.reasons


@pytest.mark.asyncio
async def test_explainer_fallback_when_llm_returns_empty():
    class _Stub:
        name = "stub"

        async def chat_json(self, *, system, user, temperature=0.3, max_tokens=700):
            return {}

    explainer = LLMExplainer(provider=_Stub())  # type: ignore[arg-type]
    explanation = await explainer.generate_explain(
        MatchScore(skills_matched=["Go"], skills_missing=["Rust"]),
        CandidateBrief(title="Backend", years=4),
        RoleBrief(title="SDE", required_skills=["Go", "Rust"], team_size=6),
    )
    # 至少 reasons + weak_points + counterfactual 都有保底
    assert explanation.reasons
    assert explanation.weak_points
    assert explanation.counterfactual["if_have"]


@pytest.mark.asyncio
async def test_explainer_clamps_score_lift():
    class _Stub:
        name = "stub"

        async def chat_json(self, *, system, user, temperature=0.3, max_tokens=700):
            return {"counterfactual": {"if_have": "x", "score_lift": 99}}

    explainer = LLMExplainer(provider=_Stub())  # type: ignore[arg-type]
    explanation = await explainer.generate_explain(
        MatchScore(),
        CandidateBrief(),
        RoleBrief(),
    )
    assert explanation.counterfactual["score_lift"] <= 0.5


# ---------------------------------------------------------------------------
# mock 函数自身鲁棒性
# ---------------------------------------------------------------------------


def test_mock_extract_helper():
    from matching.explainer_llm import _extract

    assert _extract("Role Title: Foo", "Role Title") == "Foo"
    assert _extract("nothing here", "Role Title") is None
    assert _extract("Skills Matched: A, B", "Skills Matched") == "A, B"


def test_fallback_reasons_have_meaningful_text():
    from matching.explainer_llm import _fallback_reasons

    ms = MatchScore(skills_matched=["Python", "Django"])
    cand = CandidateBrief(title="Backend Dev", years=5.0)
    role = RoleBrief(title="Senior Backend")
    out = _fallback_reasons(ms, cand, role)
    assert len(out) >= 2
    assert any("Python" in r for r in out)


def test_fallback_counterfactual_picks_missing_skill():
    from matching.explainer_llm import _fallback_counterfactual

    ms = MatchScore(skills_missing=["Rust"])
    role = RoleBrief(title="x")
    if_have, lift = _fallback_counterfactual(ms, role)
    assert "Rust" in if_have
    assert lift > 0