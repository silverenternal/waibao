"""Multi-party Interaction Agent - 多方对话协调.

需求 2.7: 智能体与相关人员及部门频繁互动(老板/HR/部门负责人/管理部门/财务).
"""
from __future__ import annotations

import json
import logging

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.toolkit import llm_call
from eventbus import emit

logger = logging.getLogger("recruittech.agents.employer.multi_party")

MULTIPARTY_PROMPT = """你是企业多方对话协调员。

各方最新输入:
{inputs}

请输出 JSON:
{{
  "stakeholders": [
    {{"role": "boss/HR/dept_head/finance/admin", "position": "立场摘要"}}
  ],
  "conflicts": ["检测到的立场冲突"],
  "proposed_resolution": "折中方案",
  "decision_summary": "汇总决策"
}}
"""


class MultiPartyAgent(BaseAgent):
    name = "multi_party_agent"
    description = "多部门多方对话协调 (2.7)"
    required_personas = ("boss", "hr", "dept_head", "admin")

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        ctx = agent_input.context or {}
        inputs = ctx.get("inputs", [])   # [{role, message, user_id}]
        if not inputs and agent_input.text:
            inputs = [{"role": "unknown", "message": agent_input.text, "user_id": agent_input.user_id}]

        try:
            raw = await llm_call(
                self.llm or LLMClient(),
                MULTIPARTY_PROMPT.format(inputs=json.dumps(inputs, ensure_ascii=False)[:3000]),
                system="你擅长多方意见汇总和冲突调解。",
                json_mode=True,
            )
            result = json.loads(raw)
        except Exception as e:
            logger.warning(f"multi_party LLM failed: {e}")
            result = {
                "stakeholders": [],
                "conflicts": [],
                "proposed_resolution": "请各方补充意见。",
                "decision_summary": "尚未达成共识",
            }

        # v6.0 EventBus — publish strategy.updated (multi-party decision)
        try:
            emit("strategy.updated", {
                "employer_id": agent_input.user_id,
                "vision_id": ctx.get("vision_id"),
                "themes": [s.get("name") for s in result.get("stakeholders", [])][:5],
                "horizon_months": 6,
            }, source="agent.multi_party")
        except Exception as _e:
            logger.debug("eventbus publish failed: %s", _e)

        return AgentOutput(
            agent_name=self.name,
            text=(
                f"👥 涉及角色: {len(result.get('stakeholders', []))} 个\n"
                f"⚠️ 冲突: {len(result.get('conflicts', []))} 个\n\n"
                f"💡 建议方案:\n{result.get('proposed_resolution', '')}\n\n"
                f"📋 决策汇总:\n{result.get('decision_summary', '')}"
            ),
            artifacts=result,
        )