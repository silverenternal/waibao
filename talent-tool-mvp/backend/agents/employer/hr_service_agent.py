"""HR Service Agent - 员工全生命周期.

需求 2.9: 智能体成为用人方的 HR,覆盖招聘→入职→培训→绩效→晋升→离职.
"""
from __future__ import annotations

import json
import logging

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.toolkit import llm_call

logger = logging.getLogger("recruittech.agents.employer.hr_service")

HR_SERVICE_PROMPT = """你是企业 HR 全生命周期助手。

员工问题: "{text}"
当前阶段: {stage}

请根据阶段给出回答。覆盖范围:
- 招聘: 进度查询、面试安排
- 入职: 流程、材料清单、入职培训
- 培训: 课程推荐、认证路径
- 绩效: 评估周期、自我评估模板
- 晋升: 通道、流程、晋升答辩
- 离职: 流程、交接清单、离职证明

涉及个人隐私/纪律问题时,建议联系直线 HR。

输出 JSON:
{{
  "stage": "recruiting/onboarding/training/performance/promotion/offboarding",
  "answer": "具体回答",
  "action_items": ["行动项"],
  "create_ticket": false,
  "escalate_to_human": false
}}
"""


STAGE_KEYWORDS = {
    "recruiting": ["面试", "招聘", "投递", "流程"],
    "onboarding": ["入职", "报到", "第一天", "材料"],
    "training": ["培训", "学习", "课程", "认证"],
    "performance": ["绩效", "考核", "评估", "KPI"],
    "promotion": ["晋升", "提拔", "升职", "晋级"],
    "offboarding": ["离职", "辞职", "交接", "last day"],
}


def _detect_stage(text: str) -> str:
    text_lower = text.lower()
    for stage, kws in STAGE_KEYWORDS.items():
        if any(kw in text for kw in kws):
            return stage
    return "general"


class HRServiceAgent(BaseAgent):
    name = "hr_service_agent"
    description = "员工全生命周期 HR 服务 (2.9)"
    required_personas = ("hr", "boss", "dept_head", "admin")

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        text = agent_input.text
        ctx = agent_input.context or {}
        stage = ctx.get("stage") or _detect_stage(text)

        try:
            raw = await llm_call(
                self.llm or LLMClient(),
                HR_SERVICE_PROMPT.format(text=text, stage=stage),
                system="你是温情专业的 HR 助手。",
                json_mode=True,
            )
            result = json.loads(raw)
        except Exception:
            result = {"stage": stage, "answer": text[:200], "action_items": [], "create_ticket": False}

        return AgentOutput(
            agent_name=self.name,
            text=result.get("answer", "我在,有什么需要帮助?"),
            artifacts=result,
        )