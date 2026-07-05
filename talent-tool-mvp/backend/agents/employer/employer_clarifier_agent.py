"""Employer Clarifier Agent - 用人方信息澄清.

需求 2.8: 智能体对海量信息澄清,产出 2.8.1 人才画像 + 2.8.2 真实需求.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import uuid4

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.toolkit import llm_call

logger = logging.getLogger("recruittech.agents.employer.clarifier")

EMPLOYER_CLARIFIER_PROMPT = """你是用人方信息整合专家。

来自各角色的输入:
- 老板 brief: {brief}
- 部门负责人 spec: {spec}
- HR 合规要求: {compliance}
- 管理制度约束: {policy}

请输出 JSON:
{{
  "talent_image": {{
    "summary": "所需人才一句话画像",
    "hard_skills": ["硬技能"],
    "soft_skills": ["软技能"],
    "experience_profile": {{"min_years": 0, "industry": [], "seniority": ""}},
    "cultural_fit": ["文化匹配关键词"]
  }},
  "real_needs": {{
    "explicit_requirements": ["表面要求(招聘JD上会写的)"],
    "implicit_requirements": ["隐性要求(真实想要的)"],
    "must_haves": ["必须有"],
    "nice_to_haves": ["最好有"],
    "deal_breakers": ["绝对不能"]
  }},
  "consensus_score": 0.0 ~ 1.0,
  "conflicts": ["多方意见冲突"],
  "follow_up_questions": ["还需要确认的问题"]
}}
"""


class EmployerClarifierAgent(BaseAgent):
    name = "employer_clarifier_agent"
    description = "用人方信息澄清 → 人才画像 + 真实需求 (2.8)"
    required_personas = ("boss", "hr", "dept_head", "admin")

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        ctx = agent_input.context or {}
        brief = ctx.get("brief", {})
        spec = ctx.get("spec", {})
        compliance = ctx.get("compliance", {})
        policy = ctx.get("policy", {})

        try:
            raw = await llm_call(
                self.llm or LLMClient(),
                EMPLOYER_CLARIFIER_PROMPT.format(
                    brief=json.dumps(brief, ensure_ascii=False)[:1500],
                    spec=json.dumps(spec, ensure_ascii=False)[:1500],
                    compliance=json.dumps(compliance, ensure_ascii=False)[:800],
                    policy=json.dumps(policy, ensure_ascii=False)[:800],
                ),
                system="你是高级猎头顾问,擅长透过表象看真实需求。",
                json_mode=True,
            )
            result = json.loads(raw)
        except Exception as e:
            logger.warning(f"employer_clarifier LLM failed: {e}")
            result = {
                "talent_image": {"summary": "信息不足"},
                "real_needs": {"explicit_requirements": [], "implicit_requirements": [],
                               "must_haves": [], "nice_to_haves": [], "deal_breakers": []},
                "consensus_score": 0.3,
                "conflicts": [],
                "follow_up_questions": ["请补充更多岗位细节"],
            }

        # 持久化
        role_id = ctx.get("role_id")
        if role_id:
            record = {
                "id": str(uuid4()),
                "organisation_id": ctx.get("organisation_id", agent_input.user_id),
                "role_id": role_id,
                "talent_image": result.get("talent_image", {}),
                "hard_skills": result.get("talent_image", {}).get("hard_skills", []),
                "soft_skills": result.get("talent_image", {}).get("soft_skills", []),
                "experience_profile": result.get("talent_image", {}).get("experience_profile", {}),
                "cultural_fit": result.get("talent_image", {}).get("cultural_fit", {}),
                "explicit_requirements": result.get("real_needs", {}).get("explicit_requirements", []),
                "implicit_requirements": result.get("real_needs", {}).get("implicit_requirements", []),
                "must_haves": result.get("real_needs", {}).get("must_haves", []),
                "nice_to_haves": result.get("real_needs", {}).get("nice_to_haves", []),
                "contributor_inputs": {"brief": brief, "spec": spec, "compliance": compliance, "policy": policy},
                "conflicts": result.get("conflicts", []),
                "consensus_score": result.get("consensus_score", 0.5),
                "follow_up_questions": result.get("follow_up_questions", []),
                "last_synthesized_at": datetime.utcnow().isoformat(),
            }
            try:
                from api.deps import get_supabase_admin
                supabase = get_supabase_admin()
                supabase.table("employer_clarifications").upsert(
                    record, on_conflict="role_id"
                ).execute()
            except Exception as e:
                logger.warning(f"failed to persist: {e}")

        return AgentOutput(
            agent_name=self.name,
            text=(
                f"🎯 人才画像: {result.get('talent_image', {}).get('summary', '信息不足')}\n\n"
                f"📌 真实需求:\n"
                f"  显性: {len(result.get('real_needs', {}).get('explicit_requirements', []))} 项\n"
                f"  隐性: {len(result.get('real_needs', {}).get('implicit_requirements', []))} 项\n"
                f"  必须: {len(result.get('real_needs', {}).get('must_haves', []))} 项\n\n"
                f"🤝 多方共识度: {int(result.get('consensus_score', 0) * 100)}%"
            ),
            artifacts=result,
        )