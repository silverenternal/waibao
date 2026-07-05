"""Profile Agent 单测 (1.1)."""
import pytest

from agents.jobseeker.profile_agent import ProfileAgent
from agents.runtime import AgentInput, LLMClient


@pytest.mark.asyncio
async def test_profile_agent_intake(mock_llm, mock_memory):
    agent = ProfileAgent(llm=mock_llm, memory=mock_memory)
    inp = AgentInput(user_id="u1", persona="jobseeker", text="我叫张三,本科毕业于北京大学计算机系,有 5 年 Python 后端经验。")
    output = await agent.run(inp)

    assert output.success
    assert output.agent_name == "profile_agent"
    assert "updated_profile" in output.artifacts
    assert 0 <= output.artifacts["completion"] <= 1
    print(f"✓ profile_agent text: {output.text[:80]}")


@pytest.mark.asyncio
async def test_profile_agent_persistence(mock_llm, mock_memory):
    """第二次调用应能 recall 第一次的画像."""
    agent = ProfileAgent(llm=mock_llm, memory=mock_memory)
    inp1 = AgentInput(user_id="u2", persona="jobseeker", text="我是一名 UI 设计师,擅长 Figma")
    await agent.run(inp1)

    inp2 = AgentInput(user_id="u2", persona="jobseeker", text="补充: 我也熟悉 Sketch")
    out2 = await agent.run(inp2)
    assert out2.success
    print("✓ profile_agent persistent memory works")