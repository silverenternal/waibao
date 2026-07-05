"""Agent 启动引导 — 注册全部 16 个 Agent."""
from __future__ import annotations

import logging

from agents.registry import registry
from agents.runtime import LLMClient
from agents.memory import CompositeMemory

logger = logging.getLogger("recruittech.agents.boot")


def init_all_agents(supabase=None):
    """注册所有 Agent 到全局 registry.

    在 main.py lifespan 中调用.
    """
    llm = LLMClient()
    memory = CompositeMemory(supabase=supabase)

    # 求职者侧 (5 个 Agent, 加上 Intake 共 6 个)
    from agents.jobseeker.profile_agent import ProfileAgent
    from agents.jobseeker.intake_agent import IntakeAgent
    from agents.jobseeker.daily_journal_agent import DailyJournalAgent
    from agents.jobseeker.emotion_agent import EmotionAgent
    from agents.jobseeker.clarifier_agent import ClarifierAgent
    from agents.jobseeker.career_planner_agent import CareerPlannerAgent

    registry.register(ProfileAgent(llm=llm, memory=memory), aliases=["profile"])
    registry.register(IntakeAgent(llm=llm, memory=memory), aliases=["intake", "upload_resume"])
    registry.register(DailyJournalAgent(llm=llm, memory=memory), aliases=["journal", "daily"])
    registry.register(EmotionAgent(llm=llm, memory=memory), aliases=["emotion", "feeling"])
    registry.register(ClarifierAgent(llm=llm, memory=memory), aliases=["clarify", "synthesis"])
    registry.register(CareerPlannerAgent(llm=llm, memory=memory), aliases=["planner", "career"])

    # 用人单位侧 (9 个 Agent)
    from agents.employer.persona_agent import PersonaAgent
    from agents.employer.compliance_agent import ComplianceAgent
    from agents.employer.vision_agent import VisionAgent
    from agents.employer.talent_brief_agent import TalentBriefAgent
    from agents.employer.job_spec_agent import JobSpecAgent
    from agents.employer.policy_agent import PolicyAgent
    from agents.employer.multi_party_agent import MultiPartyAgent
    from agents.employer.employer_clarifier_agent import EmployerClarifierAgent
    from agents.employer.hr_service_agent import HRServiceAgent

    registry.register(PersonaAgent(llm=llm, memory=memory), aliases=["hr"])
    registry.register(ComplianceAgent(llm=llm, memory=memory), aliases=["compliance", "verify"])
    registry.register(VisionAgent(llm=llm, memory=memory), aliases=["vision", "strategy"])
    registry.register(TalentBriefAgent(llm=llm, memory=memory), aliases=["brief", "talent_brief"])
    registry.register(JobSpecAgent(llm=llm, memory=memory), aliases=["spec", "job_spec"])
    registry.register(PolicyAgent(llm=llm, memory=memory), aliases=["policy"])
    registry.register(MultiPartyAgent(llm=llm, memory=memory), aliases=["multi_party", "multilogue"])
    registry.register(EmployerClarifierAgent(llm=llm, memory=memory), aliases=["employer_clarify"])
    registry.register(HRServiceAgent(llm=llm, memory=memory), aliases=["hr_service"])

    # 双向匹配 (3 个)
    from agents.evaluator.mutual_evaluator import MutualEvaluatorAgent
    registry.register(MutualEvaluatorAgent(llm=llm, memory=memory), aliases=["evaluate", "mutual"])

    logger.info(f"✅ Registered {len(registry.all_names())} agents: {registry.all_names()}")
    return registry