"""Mutual Evaluator Agent - 双方互评.

需求 3: 求职者和用人单位互相打分.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import uuid4

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.toolkit import llm_call

logger = logging.getLogger("recruittech.agents.evaluator")

MUTUAL_EVAL_PROMPT = """你是面试互评整合专家。

求职者评分:
- 专业能力: {c_skill}/5
- 沟通: {c_comm}/5
- 文化匹配: {c_culture}/5
- 发展潜力: {c_potential}/5
- 评语: {c_comment}

用人方评分:
- 专业能力: {e_skill}/5
- 沟通: {e_comm}/5
- 文化匹配: {e_culture}/5
- 发展潜力: {e_potential}/5
- 评语: {e_comment}

输出 JSON:
{{
  "mutual_score": 加权总分(0~1),
  "strengths": ["双方共识的优势"],
  "concerns": ["双方共识的顾虑"],
  "recommendation": "proceed / hold / reject",
  "next_steps": ["建议的后续动作"]
}}
"""


class MutualEvaluatorAgent(BaseAgent):
    name = "mutual_evaluator"
    description = "求职者↔用人单位 双方互评 (需求 3)"
    required_personas = ("hr", "talent_partner", "boss", "dept_head", "admin")

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        ctx = agent_input.context or {}
        cand = ctx.get("candidate_eval", {})
        emp = ctx.get("employer_eval", {})

        def s(d, k, default=3):
            return d.get(k, default)

        try:
            raw = await llm_call(
                self.llm or LLMClient(),
                "整合",
                system=MUTUAL_EVAL_PROMPT.format(
                    c_skill=s(cand, "skill"), c_comm=s(cand, "communication"),
                    c_culture=s(cand, "culture"), c_potential=s(cand, "potential"),
                    c_comment=cand.get("comment", ""),
                    e_skill=s(emp, "skill"), e_comm=s(emp, "communication"),
                    e_culture=s(emp, "culture"), e_potential=s(emp, "potential"),
                    e_comment=emp.get("comment", ""),
                ),
                json_mode=True,
            )
            result = json.loads(raw)
        except Exception as e:
            logger.warning(f"mutual eval LLM failed: {e}")
            c_avg = sum(s(cand, k) for k in ("skill", "communication", "culture", "potential")) / 4
            e_avg = sum(s(emp, k) for k in ("skill", "communication", "culture", "potential")) / 4
            mutual = (c_avg + e_avg) / 2 / 5
            result = {
                "mutual_score": mutual,
                "strengths": [],
                "concerns": [],
                "recommendation": "proceed" if mutual >= 0.7 else "hold" if mutual >= 0.5 else "reject",
                "next_steps": [],
            }

        # 持久化到 two_way_matches.feedback_loop
        candidate_id = ctx.get("candidate_id")
        role_id = ctx.get("role_id")
        if candidate_id and role_id:
            try:
                from api.deps import get_supabase_admin
                supabase = get_supabase_admin()
                supabase.table("two_way_matches").update({
                    "mutual_score": result.get("mutual_score"),
                    "feedback_loop": {
                        "evaluated_at": datetime.utcnow().isoformat(),
                        "strengths": result.get("strengths"),
                        "concerns": result.get("concerns"),
                        "recommendation": result.get("recommendation"),
                    },
                }).eq("candidate_id", str(candidate_id)).eq("role_id", str(role_id)).execute()
            except Exception as e:
                logger.warning(f"persist eval failed: {e}")

        return AgentOutput(
            agent_name=self.name,
            text=(
                f"🤝 互评分: {result.get('mutual_score', 0):.2f}\n"
                f"📌 建议: {result.get('recommendation', 'hold')}\n"
                f"✨ 共识优势: {' / '.join(result.get('strengths', [])[:3]) or '无'}"
            ),
            artifacts=result,
        )