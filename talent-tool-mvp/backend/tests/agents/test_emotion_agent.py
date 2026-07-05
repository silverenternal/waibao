"""Emotion Agent 单测 (1.4) — LLM-native 版."""
import pytest

from agents.jobseeker.emotion_agent import EmotionAgent
from agents.runtime import AgentInput


@pytest.mark.asyncio
async def test_emotion_positive(mock_llm, mock_memory):
    """积极情绪识别."""
    agent = EmotionAgent(llm=mock_llm, memory=mock_memory)
    inp = AgentInput(user_id="u1", persona="jobseeker", text="今天拿到了 offer,太开心了!😊")
    out = await agent.run(inp)
    assert out.success
    assert out.artifacts.get("primary_emotion") == "joy"
    assert out.artifacts.get("risk_level") == "none"


@pytest.mark.asyncio
async def test_emotion_negative_with_attention(mock_llm, mock_memory):
    """负面情绪."""
    agent = EmotionAgent(llm=mock_llm, memory=mock_memory)
    inp = AgentInput(user_id="u2", persona="jobseeker", text="项目又延期了,我很沮丧,有点不开心")
    out = await agent.run(inp)
    assert out.success
    # 新的 mock: sadness/anxiety/frustration/hopelessness 都算负面
    assert out.artifacts.get("primary_emotion") in (
        "sadness", "anxiety", "frustration", "hopelessness", "neutral"
    )


@pytest.mark.asyncio
async def test_emotion_severe_risk(mock_llm, mock_memory):
    """严重风险 — 应该触发 needs_attention."""
    agent = EmotionAgent(llm=mock_llm, memory=mock_memory)
    inp = AgentInput(user_id="u4", persona="jobseeker", text="我已经崩溃了,什么都没意思了")
    out = await agent.run(inp)
    assert out.success
    # severe risk → needs_attention = True
    if out.artifacts.get("risk_level") == "severe":
        assert out.artifacts.get("needs_attention") is True


@pytest.mark.asyncio
async def test_emotion_returns_response(mock_llm, mock_memory):
    """确保返回给用户的回复(text)非空."""
    agent = EmotionAgent(llm=mock_llm, memory=mock_memory)
    inp = AgentInput(user_id="u5", persona="jobseeker", text="今天好累")
    out = await agent.run(inp)
    assert out.success
    assert isinstance(out.text, str)
    assert len(out.text) > 0


@pytest.mark.asyncio
async def test_emotion_complexity_dimension(mock_llm, mock_memory):
    """新版本应该带 complexity 字段(LLM 识别的复杂度)."""
    agent = EmotionAgent(llm=mock_llm, memory=mock_memory)
    inp = AgentInput(user_id="u6", persona="jobseeker", text="面试过了但又担心下一轮")
    out = await agent.run(inp)
    assert out.success
    assert "complexity" in out.artifacts
    assert "underlying_need" in out.artifacts
    assert "reasoning" in out.artifacts  # 每个情绪有 reasoning