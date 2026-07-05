"""Career Planner Agent 单测 (1.6)."""
import pytest

from agents.jobseeker.career_planner_agent import CareerPlannerAgent
from agents.runtime import AgentInput


@pytest.mark.asyncio
async def test_career_plan_generation(mock_llm, mock_memory):
    agent = CareerPlannerAgent(llm=mock_llm, memory=mock_memory)
    inp = AgentInput(
        user_id="u1",
        persona="jobseeker",
        text="",
        context={
            "profile": {
                "name": "张三",
                "skills": [{"name": "Python"}, {"name": "React"}],
                "experience_years": 5,
            },
            "needs": {
                "explicit_needs": ["AI 产品经理"],
                "must_haves": ["前沿技术"],
            },
        },
    )
    out = await agent.run(inp)
    assert out.success
    assert "short_term" in out.artifacts
    assert "long_term" in out.artifacts
    assert "market_insights" in out.artifacts
    print(f"✓ career plan: {len(out.artifacts.get('short_term', []))} short-term items")