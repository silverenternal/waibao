"""求职者侧 - Profile Agent.

需求 1.1: 智能/知心朋友,接收求职者学历等信息.
通过对话式交互收集/校验/补全资料.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.toolkit import llm_call

logger = logging.getLogger("recruittech.agents.jobseeker.profile")


PROFILE_INTAKE_PROMPT = """你是求职者画像采集助手。

任务: 基于用户最新的输入,提取/更新画像字段,生成温和的追问(最多 2 个)。

要维护的画像字段:
- name (姓名)
- education (学历: degree + school + major + year)
- experience_years (工作年限)
- location (所在地)
- skills (技能列表)
- certifications (证书)
- portfolio (作品集)
- interests (兴趣方向)

输出 JSON:
{
  "updated_profile": { ... 字段 ... },
  "next_questions": ["问题1", "问题2"],
  "completion": 0.0 ~ 1.0,
  "warm_response": "给用户看的温暖回应"
}
"""


class ProfileAgent(BaseAgent):
    """对话式画像采集/补全 Agent."""

    name = "profile_agent"
    description = "求职者的知心朋友 + 画像采集助手(需求 1.1)"
    required_personas = ("jobseeker", "talent_partner", "admin")

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        text = agent_input.text
        ctx = agent_input.context or {}

        # 读已有画像
        existing = await self.recall(
            __import__("agents.runtime", fromlist=["MemoryScope"]).MemoryScope.long_term,
            key="profile",
            user_id=agent_input.user_id,
            default={},
        )

        system = PROFILE_INTAKE_PROMPT
        user_msg = f"已有画像: {json.dumps(existing, ensure_ascii=False)}\n用户新输入: {text}"

        raw = await llm_call(self.llm or LLMClient(), user_msg, system=system, json_mode=True)

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {"warm_response": raw, "next_questions": [], "updated_profile": {}, "completion": 0.5}

        # 合并画像
        updated = {**existing, **(result.get("updated_profile") or {})}
        await self.remember(
            __import__("agents.runtime", fromlist=["MemoryScope"]).MemoryScope.long_term,
            key="profile",
            value=updated,
            user_id=agent_input.user_id,
        )

        return AgentOutput(
            agent_name=self.name,
            text=result.get("warm_response", "好的,我记下了。"),
            artifacts={
                "updated_profile": updated,
                "next_questions": result.get("next_questions", []),
                "completion": result.get("completion", 0.5),
            },
            memory_writes=[{
                "scope": "long_term",
                "key": "profile",
                "value": updated,
            }],
        )