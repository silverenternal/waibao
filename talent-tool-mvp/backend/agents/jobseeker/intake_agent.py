"""Intake Agent - 对话式表单 + 文件上传引导.

需求 1.1 辅助: 引导求职者用对话完成建档.
"""
from __future__ import annotations

import json
import logging

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.prompts import get_prompt as _get_prompt
from agents.toolkit import llm_call
from services.profile_extractor import extract_profile_from_text, extract_profile_from_url
from eventbus import emit

logger = logging.getLogger("recruittech.agents.jobseeker.intake")

INTAKE_PROMPT = """你是建档引导助手。

根据当前"建档完成度"决定下一步:
- <30%: 邀请上传简历/补充教育背景
- 30-70%: 询问工作年限、最近公司、技能
- 70-90%: 询问兴趣方向、期望行业
- >90%: 询问期望薪资、地点

输出 JSON:
{
  "stage": "upload_resume" | "education" | "experience" | "skills" | "interests" | "compensation",
  "prompt": "引导话术",
  "expected_input": "用户应该提供什么"
}
"""


class IntakeAgent(BaseAgent):
    name = "intake_agent"
    description = "对话式引导建档助手 (1.1)"
    required_personas = ("jobseeker", "talent_partner")

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        ctx = agent_input.context or {}

        # 若提供了文件 URL
        file_url = ctx.get("file_url")
        text_to_parse = ctx.get("cv_text") or agent_input.text
        extracted = {}
        if file_url:
            extracted = await extract_profile_from_url(file_url)
        elif text_to_parse:
            extracted = await extract_profile_from_text(text_to_parse)

        completion = ctx.get("completion", 0.0)
        if extracted.get("skills"):
            completion += 0.2
        if extracted.get("experience"):
            completion += 0.2
        if extracted.get("email"):
            completion += 0.1
        completion = min(1.0, completion)

        system = _get_prompt("intake_agent", "system", default=INTAKE_PROMPT)
        user_msg = f"建档完成度: {completion:.0%}\n已抽取: {json.dumps(extracted, ensure_ascii=False)[:500]}"
        raw = await llm_call(self.llm or LLMClient(), user_msg, system=system, json_mode=True)
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {"stage": "education", "prompt": raw, "expected_input": ""}

        # v6.0 EventBus — publish profile.created on first intake
        try:
            emit("profile.created", {
                "user_id": agent_input.user_id,
                "candidate_id": ctx.get("candidate_id"),
                "initial_fields": list(extracted.keys()) if isinstance(extracted, dict) else [],
            }, source="agent.intake")
        except Exception as _e:
            logger.debug("eventbus publish failed: %s", _e)

        return AgentOutput(
            agent_name=self.name,
            text=result.get("prompt", "请告诉我一些你的基本信息吧"),
            artifacts={
                "stage": result.get("stage"),
                "expected_input": result.get("expected_input"),
                "extracted": extracted,
                "completion": completion,
            },
            memory_writes=[{
                "scope": "long_term",
                "key": "intake_state",
                "value": {"completion": completion, "stage": result.get("stage")},
            }],
        )