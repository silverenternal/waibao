"""Vision Agent - 愿景/规划/战略/战术传达与结构化.

需求 2.3: 老板把企业愿景、规划、战略、战术向智能体传达.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import uuid4

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.prompts import get_prompt as _get_prompt
from agents.toolkit import llm_call
from eventbus import emit

logger = logging.getLogger("recruittech.agents.employer.vision")


def _as_dict(raw: str | bytes) -> dict:
    """Defensively parse an LLM JSON payload into a dict.

    Local LLMs occasionally return a JSON array / scalar; the downstream
    ``result.get(...)`` calls would otherwise raise AttributeError. Non-dict
    payloads fall back to ``{}``.
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


VISION_PROMPT = """你是企业战略解码专家。

老板输入:
"{text}"

请解构为 4 层 + 识别空白:
{{
  "vision": {{"statement": "愿景一句话", "horizon": "3-5年"}},
  "planning": {{"statement": "1年规划", "horizon": "1年"}},
  "strategy": {{"statement": "年度战略重点", "horizon": "1年"}},
  "tactic": [{{"title": "战术动作", "horizon": "季度", "owner": "责任部门"}}],
  "gaps": ["还缺什么没说"],
  "follow_up_questions": ["需要老板补充的问题"]
}}
"""


class VisionAgent(BaseAgent):
    name = "vision_agent"
    description = "愿景/规划/战略/战术解码 (2.3)"
    required_personas = ("boss", "hr", "admin")

    LEVEL_MAP = {"vision": "vision", "planning": "planning", "strategy": "strategy", "tactic": "tactic"}

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        text = agent_input.text
        ctx = agent_input.context or {}
        organisation_id = ctx.get("organisation_id", agent_input.user_id)

        raw = await llm_call(
            self.llm or LLMClient(),
            _get_prompt("vision_agent", "system", default=VISION_PROMPT).format(text=text),
            system="你是顶级战略顾问,擅长把老板的口述结构化为可落地的 4 层战略。",
            json_mode=True,
        )
        result = _as_dict(raw)
        if not result:
            result = {
                "vision": {"statement": text[:100], "horizon": "3年"},
                "planning": {}, "strategy": {}, "tactic": [],
                "gaps": [], "follow_up_questions": ["能否更具体描述愿景?"],
            }

        # 持久化
        records = []
        parent_id = None
        for level in ("vision", "planning", "strategy", "tactic"):
            section = result.get(level, {})
            if isinstance(section, dict) and section.get("statement"):
                records.append({
                    "organisation_id": organisation_id,
                    "level": level,
                    "horizon": section.get("horizon"),
                    "title": list(section.get("statement", ""))[:30] if isinstance(section.get("statement"), str) else str(section.get("statement"))[:30],
                    "description": section.get("statement", "") if isinstance(section.get("statement"), str) else json.dumps(section, ensure_ascii=False),
                    "owner_role": "boss",
                    "owner_user_id": agent_input.user_id,
                    "status": "active",
                    "parent_id": parent_id,
                })
            elif level == "tactic" and isinstance(section, list):
                for t in section:
                    records.append({
                        "organisation_id": organisation_id,
                        "level": "tactic",
                        "horizon": t.get("horizon"),
                        "title": t.get("title", ""),
                        "description": t.get("title", ""),
                        "owner_role": t.get("owner", "boss"),
                        "owner_user_id": agent_input.user_id,
                        "status": "active",
                        "parent_id": parent_id,
                    })

        try:
            from api.deps import get_supabase_admin
            supabase = get_supabase_admin()
            for r in records:
                resp = supabase.table("company_strategy").insert(r).execute()
                if resp.data:
                    if not parent_id:
                        parent_id = resp.data[0]["id"]
        except Exception as e:
            logger.warning(f"failed to persist strategy: {e}")

        # v6.0 EventBus — publish strategy.updated
        try:
            emit("strategy.updated", {
                "employer_id": agent_input.user_id,
                "vision_id": parent_id,
                "themes": [t.get("title") for t in (result.get("tactic") or []) if isinstance(t, dict)][:5],
                "horizon_months": 12,
            }, source="agent.vision")
        except Exception as _e:
            logger.debug("eventbus publish failed: %s", _e)

        return AgentOutput(
            agent_name=self.name,
            text=(
                f"🎯 愿景: {result.get('vision', {}).get('statement', '未提取')}\n"
                f"📅 1年规划: {result.get('planning', {}).get('statement', '未提取')}\n"
                f"🚀 年度战略: {result.get('strategy', {}).get('statement', '未提取')}\n"
                f"⚙️ 战术动作: {len(result.get('tactic', []))} 项\n\n"
                f"❓ 追问: {', '.join(result.get('follow_up_questions', [])[:3]) or '无'}"
            ),
            artifacts=result,
        )