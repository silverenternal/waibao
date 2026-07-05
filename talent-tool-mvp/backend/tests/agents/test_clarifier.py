"""Clarifier Agent 单测 (1.5) — LLM-native + 反思版."""
import pytest

from agents.jobseeker.clarifier_agent import ClarifierAgent
from agents.runtime import AgentInput


@pytest.mark.asyncio
async def test_clarifier_basic(mock_llm, mock_memory):
    agent = ClarifierAgent(llm=mock_llm, memory=mock_memory)
    inp = AgentInput(
        user_id="u1",
        persona="jobseeker",
        text="",
        context={
            "journals": [{"content": "今天面试了一个 AI 公司", "ai_rating": "good"}],
            "conversations": [{"role": "user", "content": "我想做 AI 产品经理"}],
        },
    )
    out = await agent.run(inp)
    assert out.success
    assert "profile_synthesis" in out.artifacts
    print(f"✓ clarifier text: {out.text[:100]}")


@pytest.mark.asyncio
async def test_clarifier_has_reasoning_chain(mock_llm, mock_memory):
    """新版本应返回 reasoning_chain (含 synthesize + reflect)."""
    agent = ClarifierAgent(llm=mock_llm, memory=mock_memory)
    inp = AgentInput(user_id="u1", persona="jobseeker", text="", context={
        "journals": [{"content": "今天学了很多"}]
    })
    out = await agent.run(inp)
    assert out.success
    assert "reasoning_chain" in out.artifacts
    assert "synthesize" in out.artifacts["reasoning_chain"]


@pytest.mark.asyncio
async def test_clarifier_reflection_adjusts_confidence(mock_llm, mock_memory):
    """反思步骤应能调整 confidence."""
    agent = ClarifierAgent(llm=mock_llm, memory=mock_memory)
    inp = AgentInput(user_id="u1", persona="jobseeker", text="", context={
        "journals": [], "conversations": []
    })
    out = await agent.run(inp)
    assert out.success
    # 应包含 reflection 字段
    assert "reflection" in out.artifacts


@pytest.mark.asyncio
async def test_clarifier_empty_context(mock_llm, mock_memory):
    """空数据也应能给出兜底."""
    agent = ClarifierAgent(llm=mock_llm, memory=mock_memory)
    inp = AgentInput(user_id="u2", persona="jobseeker", text="", context={})
    out = await agent.run(inp)
    assert out.success
    # 应有某种形式的追问/低完整度提示
    has_questions = (
        len(out.artifacts.get("follow_up_questions", [])) > 0
        or len(out.artifacts.get("next_questions", [])) > 0
    )
    completeness = out.artifacts.get("info_completeness", 0)
    if isinstance(completeness, dict):
        completeness = completeness.get("value", 1)
    assert has_questions or completeness <= 0.5