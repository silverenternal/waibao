"""Job Spec Agent - 部门负责人描述具体细节.

需求 2.5: 用人相关部门负责人描述具体细节.
"""
from __future__ import annotations

import json
import logging

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.prompts import get_prompt as _get_prompt
from agents.toolkit import llm_call
from eventbus import emit

logger = logging.getLogger("recruittech.agents.employer.job_spec")

JOB_SPEC_PROMPT = """你是部门负责人的需求细化助手。

口语化描述:
"{text}"

请输出 JSON:
{{
  "responsibilities": ["岗位职责1", "岗位职责2"],
  "hard_requirements": [
    {{"category": "技能/经验/学历/证书", "value": "...", "min_years": 0}}
  ],
  "nice_to_haves": ["加分项1"],
  "team_culture": {{
    "work_style": "协作风格",
    "pace": "节奏",
    "autonomy": "自主度"
  }},
  "reporting_line": "汇报关系",
  "tech_stack": ["技术栈"],
  "travel_required": "0%~30%",
  "draft_jd": "完整 JD 草稿(可发布版本)",
  "over_spec_flags": ["要求可能过高/不合理的地方"]
}}
"""


class JobSpecAgent(BaseAgent):
    name = "job_spec_agent"
    description = "部门负责人细化 JD (2.5)"
    required_personas = ("dept_head", "hr", "boss", "admin")

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        text = agent_input.text
        ctx = agent_input.context or {}
        role_id = ctx.get("role_id")

        try:
            raw = await llm_call(
                self.llm or LLMClient(),
                _get_prompt("job_spec_agent", "system", default=JOB_SPEC_PROMPT).format(text=text),
                system="你是有 15 年经验的招聘专家,熟悉各行业 JD 套路。",
                json_mode=True,
            )
            result = json.loads(raw)
        except Exception as e:
            logger.warning(f"job_spec LLM failed: {e}")
            result = {
                "responsibilities": [text[:200]],
                "hard_requirements": [],
                "nice_to_haves": [],
                "team_culture": {},
                "draft_jd": text[:500],
                "over_spec_flags": [],
            }

        # 如果指定了 role_id,更新 roles 表
        if role_id:
            try:
                from api.deps import get_supabase_admin
                supabase = get_supabase_admin()
                supabase.table("roles").update({
                    "description": result.get("draft_jd", text),
                    "required_skills": [
                        {"name": r.get("value"), "importance": "required"}
                        for r in result.get("hard_requirements", [])
                        if r.get("category") == "技能"
                    ],
                    "preferred_skills": [
                        {"name": nh} for nh in result.get("nice_to_haves", [])
                        if isinstance(nh, str)
                    ],
                }).eq("id", str(role_id)).execute()
            except Exception as e:
                logger.warning(f"failed to update role: {e}")

        over_spec = result.get("over_spec_flags", [])
        warning = ""
        if over_spec:
            warning = "\n\n⚠️ 检测到过度要求:\n" + "\n".join(f"  - {x}" for x in over_spec)

        # v6.0 EventBus — publish role.image.updated (JD produced)
        try:
            emit("role.image.updated", {
                "employer_id": agent_input.user_id,
                "role_id": ctx.get("role_id"),
                "traits": [c.get("value") for c in result.get("hard_requirements", [])][:5],
                "must_haves": [c.get("value") for c in result.get("hard_requirements", [])][:5],
            }, source="agent.job_spec")
        except Exception as _e:
            logger.debug("eventbus publish failed: %s", _e)

        return AgentOutput(
            agent_name=self.name,
            text=(
                f"📄 JD 草稿已生成。\n\n"
                f"核心职责 {len(result.get('responsibilities', []))} 项 / "
                f"硬性要求 {len(result.get('hard_requirements', []))} 项 / "
                f"加分项 {len(result.get('nice_to_haves', []))} 项"
                + warning
            ),
            artifacts=result,
        )