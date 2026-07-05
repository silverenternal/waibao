"""Daily Journal Agent - 接收每日工作内容,触发 Advisor Agent.

需求 1.2: 即时更新工作状态,智能体给出评价/建议/注意事项.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import UUID, uuid4

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient, MemoryScope
from agents.toolkit import llm_call

logger = logging.getLogger("recruittech.agents.jobseeker.journal")

JOURNAL_PROMPT = """你是求职者的工作教练。

用户描述了今天的工作内容/困惑/心得:
"{text}"

请生成 JSON 响应:
{{
  "rating": "excellent" | "good" | "needs_improvement",
  "advice": "2-3 句具体建议",
  "warnings": ["风险点1", "风险点2"],
  "action_items": ["明天可以做的事1", "明天可以做的事2"],
  "mood_score": -1.0 ~ 1.0,
  "topics": ["关键词1", "关键词2"]
}}
"""


class DailyJournalAgent(BaseAgent):
    name = "daily_journal_agent"
    description = "日报摄取 + AI 评价(需求 1.2)"
    required_personas = ("jobseeker", "talent_partner")

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        text = agent_input.text
        ctx = agent_input.context or {}
        today = datetime.utcnow().date().isoformat()

        system = "你是一位有 10 年经验的职业教练,语言温暖但一针见血。"
        user_msg = JOURNAL_PROMPT.format(text=text)
        raw = await llm_call(self.llm or LLMClient(), user_msg, system=system, json_mode=True)

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {
                "rating": "good",
                "advice": text[:100],
                "warnings": [],
                "action_items": [],
                "mood_score": 0.0,
                "topics": [],
            }

        # 写日报到 Supabase
        journal_record = {
            "id": str(uuid4()),
            "user_id": agent_input.user_id,
            "journal_date": today,
            "content": text,
            "mood_score": result.get("mood_score", 0.0),
            "topics": result.get("topics", []),
            "ai_rating": result.get("rating"),
            "ai_advice": result.get("advice"),
            "ai_warnings": result.get("warnings", []),
            "ai_action_items": result.get("action_items", []),
            "advisor_agent": "daily_journal_agent",
            "reviewed_at": datetime.utcnow().isoformat(),
        }
        try:
            from api.deps import get_supabase_admin
            supabase = get_supabase_admin()
            supabase.table("daily_journals").upsert(
                journal_record,
                on_conflict="user_id,journal_date",
            ).execute()
        except Exception as e:
            logger.warning(f"failed to persist journal: {e}")

        return AgentOutput(
            agent_name=self.name,
            text=(
                f"📝 评价: **{result.get('rating', 'good')}**\n\n"
                f"💡 建议: {result.get('advice', '')}\n\n"
                f"⚠️ 注意事项: {' / '.join(result.get('warnings', [])) or '无'}\n\n"
                f"🎯 明天行动: {' / '.join(result.get('action_items', [])) or '继续保持'}"
            ),
            artifacts={
                "rating": result.get("rating"),
                "advice": result.get("advice"),
                "warnings": result.get("warnings"),
                "action_items": result.get("action_items"),
                "mood_score": result.get("mood_score"),
            },
            signals=[{
                "type": "journal_logged",
                "rating": result.get("rating"),
                "mood": result.get("mood_score"),
            }],
        )