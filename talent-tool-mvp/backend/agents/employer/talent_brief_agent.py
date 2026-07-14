"""Talent Brief Agent — 用 LLM 检测偏见(不再硬编码词表)."""
from __future__ import annotations

import json
import logging

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.llm_extractor import detect_biases
from agents.prompts import get_prompt as _get_prompt

logger = logging.getLogger("recruittech.agents.employer.talent_brief")


SYSTEM = """你是企业人才需求顾问。

你的职责:
1. 提取老板描述中的硬约束和软偏好
2. **主动发现偏见** (年龄/性别/学历/婚育/地域/...) - 用温和的方式指出
3. 推断老板没说但可能存在的隐性需求
4. 生成人才画像初稿

输出风格:
- 不照搬老板原话,而是结构化提炼
- 偏见提示要委婉,说明为什么是问题(用数据/法律/招聘市场事实)
- 给出可操作建议
"""


class TalentBriefAgent(BaseAgent):
    """LLM-native 偏见检测 + 画像生成."""

    name = "talent_brief_agent"
    description = "老板描述人才框架 + 偏见检测 (2.4)"
    required_personas = ("boss", "hr", "admin")

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        text = agent_input.text
        ctx = agent_input.context or {}

        # 1. 偏见检测(LLM 自己发现,不靠关键词)
        bias_result = await detect_biases(self.llm or LLMClient(), text)

        # 2. 提炼人才画像(同时进行)
        schema = """
{
  "hard_constraints": [
    {"category": "行业/职级/技能/...", "value": "...", "importance": "must/should", "rationale": "老板为什么提这个"}
  ],
  "soft_preferences": [
    {"preference": "软偏好", "rationale": "为什么老板隐含希望"}
  ],
  "implicit_requirements": [
    {"req": "隐性需求", "inferred_from": "推断依据", "confidence": 0~1}
  ],
  "talent_image_draft": {
    "summary": "一句话人才画像",
    "background": "背景倾向",
    "potential_direction": "潜力方向",
    "values": ["价值观关键词"],
    "red_flags_to_avoid": ["老板没说但可能不喜欢的"]
  },
  "smart_questions_for_boss": [
    {"question": "应该问老板的问题", "purpose": "为什么问"}
  ]
}
"""
        from agents.toolkit import llm_call
        from eventbus import emit
        try:
            raw = await llm_call(
                self.llm or LLMClient(),
                text + "\n\n参考偏见分析:\n" + json.dumps(bias_result, ensure_ascii=False)[:1500],
                system=_get_prompt("talent_brief_agent", "system", default=SYSTEM),
                json_mode=True,
            )
            result = json.loads(raw)
        except Exception as e:
            logger.warning(f"brief failed: {e}")
            result = {"hard_constraints": [], "soft_preferences": [], "talent_image_draft": {}}

        # 3. 合并偏见分析
        result["bias_analysis"] = bias_result
        result["fairness_score"] = bias_result.get("fairness_score", 1.0)

        # 4. 组装回复(包含偏见提醒)
        warnings_text = ""
        demo_biases = bias_result.get("demographic_bias", [])
        if demo_biases:
            warnings_text = "\n\n💡 我注意到几个可能值得重新考虑的地方:\n"
            for b in demo_biases[:3]:
                warnings_text += (
                    f"  - {b.get('type', '...')}: {b.get('concern', '')}\n"
                    f"    建议: {b.get('suggestion', '')}\n"
                )
            warnings_text += (
                "\n我不是指责,而是想帮您扩大候选人池。"
                "研究表明,无明确标准的偏好会显著降低招聘质量。"
            )

        # v6.0 EventBus — publish role.image.updated (from talent brief)
        try:
            emit("role.image.updated", {
                "employer_id": agent_input.user_id,
                "role_id": ctx.get("role_id"),
                "traits": [c.get("value") for c in result.get("hard_constraints", [])][:5],
                "must_haves": [c.get("value") for c in result.get("hard_constraints", [])][:5],
            }, source="agent.talent_brief")
        except Exception as _e:
            logger.debug("eventbus publish failed: %s", _e)

        return AgentOutput(
            agent_name=self.name,
            text=(
                f"📋 人才画像草稿:\n{result.get('talent_image_draft', {}).get('summary', '')}\n\n"
                f"🔒 硬约束: {len(result.get('hard_constraints', []))} 项\n"
                f"💭 软偏好: {len(result.get('soft_preferences', []))} 项\n"
                f"🤔 隐性需求(LLM 推断): {len(result.get('implicit_requirements', []))} 项\n"
                f"⚖️ 公平性评分: {int(bias_result.get('fairness_score', 1.0) * 100)}%"
                + warnings_text
            ),
            artifacts=result,
        )