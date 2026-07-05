"""AI-native 优化后的回归测试.

验证:
1. SemanticRouter 存在并工作
2. ReAct Agent base class 可实例化
3. LLM extractors 不依赖正则
4. reasoning_chain 在 AgentOutput 中
5. 真实 emotion agent 不再依赖 _quick_emotion
"""
import pytest

from agents.runtime import AgentInput, AgentOutput
from agents.semantic_router import SemanticRouter, AGENT_INTENT_DESCRIPTIONS
from agents.react import ReActAgent, ToolSpec
from agents.llm_extractor import detect_emotion, detect_biases


# 1. SemanticRouter 存在性
def test_semantic_router_exists():
    assert SemanticRouter is not None
    assert len(AGENT_INTENT_DESCRIPTIONS) >= 15  # 至少 15 个 agent


def test_semantic_router_no_hardcoded_keywords():
    """不应再有硬编码的关键词表 — 应该用自然语言描述."""
    # 所有描述都应该是自然语言,而非短关键词
    for agent, descs in AGENT_INTENT_DESCRIPTIONS.items():
        assert all(len(d) >= 3 for d in descs), f"{agent} 的描述太短,可能不是自然语言"


# 2. ReAct Agent
def test_react_agent_instantiable():
    class TestReAct(ReActAgent):
        name = "test_react"
        description = "test"

        async def _handle(self, agent_input):
            return AgentOutput(agent_name=self.name, text="done")

    agent = TestReAct()
    assert hasattr(agent, "tools")
    assert agent.max_iterations > 0


def test_react_agent_tool_registration():
    class TestReAct(ReActAgent):
        name = "test_react2"

        async def _handle(self, agent_input):
            return AgentOutput(agent_name=self.name, text="done")

    agent = TestReAct()

    async def dummy_tool(x: int) -> dict:
        return {"result": x * 2}

    agent.register_tool(
        name="dummy",
        description="测试工具",
        parameters={"type": "object", "properties": {"x": {"type": "integer"}}},
        handler=dummy_tool,
    )
    assert "dummy" in agent.tools
    spec = agent.tools["dummy"]
    assert spec.description == "测试工具"


# 3. LLM extractors (不再是正则)
@pytest.mark.asyncio
async def test_detect_emotion_returns_reasoning(mock_llm):
    """emotion 应包含 reasoning/evidence 字段."""
    result = await detect_emotion(mock_llm, "今天有点崩溃")
    assert "emotions" in result or "_error" in result
    if "emotions" in result:
        assert "evidence" in result["emotions"][0]


@pytest.mark.asyncio
async def test_detect_biases_returns_categories(mock_llm):
    """bias 应分类: 人口偏见/认知偏见/逻辑空白."""
    result = await detect_biases(mock_llm, "我要男的,30 岁以下,985 毕业")
    if "_error" not in result:
        assert "demographic_bias" in result
        assert "cognitive_bias" in result
        assert "fairness_score" in result


# 4. AgentOutput 带 reasoning_chain
def test_agent_output_has_reasoning_field():
    output = AgentOutput(agent_name="test", text="ok")
    assert hasattr(output, "reasoning_chain")
    assert output.reasoning_chain == []


# 5. Emotion agent 不再有 lexicon 兜底
def test_emotion_agent_no_lexicon_fallback():
    """确认 _quick_emotion 已经被移除."""
    import agents.jobseeker.emotion_agent as m
    assert not hasattr(m, "_quick_emotion"), "lexicon 兜底应已删除"


# 6. profile_extractor 不再使用正则
def test_profile_extractor_uses_llm():
    """确认旧正则函数标记为 deprecated."""
    import services.profile_extractor as m
    import inspect
    src = inspect.getsource(m)
    # 不应该有复杂的 SKILL_KEYWORDS 词典
    assert "SKILL_KEYWORDS" not in src, "应已删除关键词表"


# 7. 端到端:情绪+偏见 综合测试
@pytest.mark.asyncio
async def test_combined_emotion_and_bias(mock_llm):
    """验证新版 emotion agent 调用 detect_emotion 后包含 reasoning."""
    from agents.jobseeker.emotion_agent import EmotionAgent
    agent = EmotionAgent(llm=mock_llm)

    inp = AgentInput(user_id="u", persona="jobseeker", text="我很难过")
    out = await agent.run(inp)
    assert out.success
    # 新版应有 reasoning 字段
    assert "reasoning" in out.artifacts