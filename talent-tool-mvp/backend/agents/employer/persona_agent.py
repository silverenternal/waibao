"""用人单位 Persona Agent - 真诚HR的人格基底.

需求 2.1 / 2.9: 真诚HR,老板得力助手; 员工全生命周期服务.
"""
from __future__ import annotations

import json
import logging

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.toolkit import llm_call

logger = logging.getLogger("recruittech.agents.employer.persona")

HR_PERSONA_SYSTEM = """你是用人单位的"真诚HR"人格化身。

性格:
- 专业、有同理心、不卑不亢
- 主动思考公司长期利益,而非短期凑数
- 对老板敢说真话,对求职者保持尊重
- 严格遵守劳动法和候选人隐私

回答时:
1. 先复述确认你理解的问题
2. 再给出方案/建议
3. 列出风险点和边界
4. 必要时建议联系直线 HR(涉及个人隐私/纪律问题)
"""


class PersonaAgent(BaseAgent):
    name = "persona_agent"
    description = "真诚HR人格基底 + 员工全生命周期 (2.1 / 2.9)"
    required_personas = ("hr", "boss", "admin")

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        text = agent_input.text
        ctx = agent_input.context or {}

        # 边界检查
        sensitive_topics = ["工资条", "个税", "社保", "开除", "解雇"]
        if any(t in text for t in sensitive_topics) and ctx.get("asker_role") != "owner":
            return AgentOutput(
                agent_name=self.name,
                text="这个问题涉及个人隐私,建议联系直线 HR 或 HRBP 单独沟通。我可以帮你创建工单。",
                artifacts={"create_ticket": True},
            )

        raw = await llm_call(self.llm or LLMClient(), text, system=HR_PERSONA_SYSTEM)

        return AgentOutput(
            agent_name=self.name,
            text=raw,
            artifacts={"persona": "sincere_hr"},
        )