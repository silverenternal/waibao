"""端到端匹配流程集成测试."""
import pytest

from agents.runtime import AgentInput, LLMClient
from agents.jobseeker.profile_agent import ProfileAgent
from agents.jobseeker.emotion_agent import EmotionAgent
from agents.jobseeker.daily_journal_agent import DailyJournalAgent
from agents.jobseeker.clarifier_agent import ClarifierAgent
from agents.jobseeker.career_planner_agent import CareerPlannerAgent
from agents.employer.vision_agent import VisionAgent
from agents.employer.job_spec_agent import JobSpecAgent
from agents.employer.compliance_agent import ComplianceAgent
from agents.evaluator.mutual_evaluator import MutualEvaluatorAgent
from matching.two_way import compute_two_way


@pytest.mark.asyncio
async def test_jobseeker_full_flow(mock_llm, mock_memory):
    """求职者完整流程: 建档→日记→情感→澄清→规划."""
    llm = mock_llm

    # 1. Profile
    profile = ProfileAgent(llm=llm, memory=mock_memory)
    await profile.run(AgentInput(user_id="u1", persona="jobseeker", text="我是李四,Python 后端,3 年经验,想转 AI 方向"))

    # 2. Daily Journal
    journal = DailyJournalAgent(llm=llm, memory=mock_memory)
    jout = await journal.run(AgentInput(user_id="u1", persona="jobseeker", text="今天学了 LangChain 基础"))
    assert jout.artifacts["rating"] in ("excellent", "good", "needs_improvement")

    # 3. Emotion
    emo = EmotionAgent(llm=llm, memory=mock_memory)
    eout = await emo.run(AgentInput(user_id="u1", persona="jobseeker", text="面试挂了,有点沮丧"))
    assert eout.artifacts["sentiment"] < 0

    # 4. Clarifier
    clar = ClarifierAgent(llm=llm, memory=mock_memory)
    clout = await clar.run(AgentInput(
        user_id="u1", persona="jobseeker", text="",
        context={
            "journals": [{"content": "今天学了 LangChain", "ai_rating": "good"}],
            "conversations": [{"role": "user", "content": "想转 AI"}],
        },
    ))
    assert "profile_synthesis" in clout.artifacts

    # 5. Career Planner
    planner = CareerPlannerAgent(llm=llm, memory=mock_memory)
    pout = await planner.run(AgentInput(
        user_id="u1", persona="jobseeker", text="",
        context={
            "profile": {"skills": [{"name": "Python"}]},
            "needs": {"explicit_needs": ["AI"]},
        },
    ))
    assert "short_term" in pout.artifacts
    print("✓ jobseeker full flow passed")


@pytest.mark.asyncio
async def test_employer_full_flow(mock_llm, mock_memory):
    """用人单位完整流程: 合规→愿景→JD→人才画像."""
    llm = mock_llm

    # 1. Compliance
    comp = ComplianceAgent(llm=llm, memory=mock_memory)
    cout = await comp.run(AgentInput(
        user_id="org1", persona="hr", text="",
        context={"file_url": "https://example.com/license.jpg", "credential_type": "business_license"},
    ))
    assert cout.success

    # 2. Vision
    vision = VisionAgent(llm=llm, memory=mock_memory)
    vout = await vision.run(AgentInput(
        user_id="boss1", persona="boss", text="我们公司要在 3 年内成为国内最领先的 AI Agent 平台",
    ))
    assert "vision" in vout.artifacts or vout.success

    # 3. Job Spec
    spec = JobSpecAgent(llm=llm, memory=mock_memory)
    sout = await spec.run(AgentInput(
        user_id="boss1", persona="dept_head",
        text="招一个 AI 工程师,熟悉 Python/LangChain,有 LLM 项目经验,能独立做产品",
    ))
    assert "draft_jd" in sout.artifacts
    print("✓ employer full flow passed")


@pytest.mark.asyncio
async def test_two_way_match_flow(mock_llm):
    """双向匹配闭环."""
    cand = {"skills": [{"name": "Python"}, {"name": "LangChain"}], "experience_years": 4}
    role = {
        "required_skills": [{"name": "Python"}, {"name": "LangChain"}],
        "min_experience_years": 3,
        "culture": "AI 前沿",
    }
    score = await compute_two_way(cand, role, {"must_haves": []}, {}, llm=mock_llm)
    assert score.harmonic_score > 0.5
    print(f"✓ two-way match: h={score.harmonic_score:.2f}")


@pytest.mark.asyncio
async def test_mutual_evaluation(mock_llm, mock_memory):
    """互评 Agent."""
    eval_agent = MutualEvaluatorAgent(llm=mock_llm, memory=mock_memory)
    out = await eval_agent.run(AgentInput(
        user_id="hr1", persona="hr", text="",
        context={
            "candidate_eval": {"skill": 4, "communication": 5, "culture": 4, "potential": 5, "comment": "技术扎实"},
            "employer_eval": {"skill": 4, "communication": 4, "culture": 5, "potential": 4, "comment": "文化契合"},
        },
    ))
    assert out.success
    print(f"✓ mutual eval: {out.artifacts.get('recommendation')}")