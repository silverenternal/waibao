"""Daily Journal Agent - 接收每日工作内容,触发 Advisor Agent.

v8.1 T3602: 按 10 角色行业定制评价 prompt + 输出更结构化评价.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import UUID, uuid4

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.toolkit import llm_call
from eventbus import emit

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
    description = "日报摄取 + AI 评价 (需求 1.2, v8.1 行业垂直)"
    required_personas = ("jobseeker", "talent_partner")

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        text = agent_input.text
        ctx = agent_input.context or {}
        today = datetime.utcnow().date().isoformat()
        role = ctx.get("industry_role") or ctx.get("role") or "backend"

        # v8.1 - 行业垂直 prompt
        try:
            from services.jobseeker.journal_evaluator import build_prompt, ROLE_DISPLAY
            system_prompt = (
                f"你是一位有 10 年经验的 {ROLE_DISPLAY.get(role, role)} 行业的职业教练,"
                "语言温暖但一针见血。"
            )
            user_msg = build_prompt(role, text)
        except Exception as e:
            logger.debug("journal evaluator import failed: %s", e)
            system_prompt = "你是一位有 10 年经验的职业教练,语言温暖但一针见血。"
            user_msg = JOURNAL_PROMPT.format(text=text)

        raw = await llm_call(
            self.llm or LLMClient(), user_msg, system=system_prompt, json_mode=True
        )

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

        # v8.1 - 写 action_items 状态机
        action_items_v2 = []
        try:
            from services.jobseeker.journal_evaluator import get_journal_evaluator
            evaluator = get_journal_evaluator()
            parsed_for_evaluator = {
                "score": _rating_to_score(result.get("rating", "good")),
                "dimension_scores": result.get("dimension_scores", {}),
                "strengths": [],
                "improvements": [result.get("advice", "")] if result.get("advice") else [],
                "risks": result.get("warnings", []),
                "action_items": [
                    {"title": ai, "feasibility": 3} if isinstance(ai, str) else ai
                    for ai in (result.get("action_items") or [])
                ],
            }
            evaluation = evaluator.evaluate(
                text=text,
                role=role,
                context={"user_id": agent_input.user_id},
                parsed=parsed_for_evaluator,
            )
            action_items_v2 = [ai.to_dict() for ai in evaluation.action_items]
        except Exception as e:
            logger.debug("evaluator failed: %s", e)

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
            "industry_role": role,
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
        except Exception:
            pass

        try:
            emit("journal.submitted", {
                "user_id": agent_input.user_id,
                "journal_id": journal_record["id"],
                "role": role,
                "mood": result.get("mood_score"),
                "summary": result.get("advice"),
                "ts": journal_record.get("journal_date"),
                "action_items_count": len(action_items_v2),
            }, source="agent.daily_journal")
        except Exception:
            pass

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
                "industry_role": role,
                "action_items_v2": action_items_v2,
            },
            signals=[{
                "type": "journal_logged",
                "rating": result.get("rating"),
                "mood": result.get("mood_score"),
                "role": role,
            }],
        )


def _rating_to_score(rating):
    return {
        "excellent": 9.0,
        "good": 7.0,
        "needs_improvement": 4.5,
    }.get(str(rating).lower(), 6.0)