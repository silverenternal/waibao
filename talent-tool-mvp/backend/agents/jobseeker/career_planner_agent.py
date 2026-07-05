"""Career Planner Agent - 职业规划师/顾问.

需求 1.6: 多层次职业规划,基于画像+真实需求+市场行情.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import uuid4

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.toolkit import llm_call, search_web

logger = logging.getLogger("recruittech.agents.jobseeker.career_planner")

PLANNER_PROMPT = """你是求职者的高级职业规划顾问。

用户画像:
{profile}

用户真实需求:
{needs}

市场行情参考:
{market}

请生成 JSON:
{{
  "short_term": [
    {{"title": "行动标题", "detail": "具体描述", "duration": "1-2 周", "priority": "high/medium/low"}}
  ],
  "mid_term": [
    {{"title": "...", "detail": "...", "duration": "1-3 个月", "milestone": "可量化目标"}}
  ],
  "long_term": [
    {{"title": "...", "detail": "...", "duration": "1-3 年", "outcome": "最终成果"}}
  ],
  "learning_paths": [
    {{"topic": "技能名", "resources": [{{"type": "course/book/cert", "name": "...", "url": "..."}}]}}
  ],
  "recommended_roles": [
    {{"title": "推荐岗位", "reason": "匹配理由", "match_score": 0~1}}
  ],
  "skill_gaps": [
    {{"skill": "缺失技能", "importance": "high/medium/low", "acquisition_difficulty": "easy/medium/hard"}}
  ],
  "milestones": [
    {{"date": "时间", "target": "里程碑目标"}}
  ]
}}
"""


async def fetch_market_insights(skills: list[str], target_role: str | None) -> dict:
    """拉取市场行情(MVP: mock; 生产接招聘网站 API)."""
    results = []
    for kw in (skills[:3] if skills else []):
        r = await search_web(f"{kw} 招聘 2026 薪资", top_k=3)
        results.append({"keyword": kw, "results": r})
    return {
        "salary_trends": {"python": "20-50k/月", "react": "18-40k/月"},
        "hot_skills": ["AI/LLM", "云原生", "Rust"],
        "sources": results,
    }


class CareerPlannerAgent(BaseAgent):
    name = "career_planner_agent"
    description = "职业规划师/顾问(需求 1.6)"
    required_personas = ("jobseeker", "talent_partner", "admin")

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        ctx = agent_input.context or {}

        # 1. 拉取最新画像/需求
        profile = ctx.get("profile", {})
        needs = ctx.get("needs", {})
        target_role = ctx.get("target_role") or (needs.get("explicit_needs") or [""])[0]

        # 2. 拉取市场行情
        market = await fetch_market_insights(
            [s.get("name") for s in profile.get("skills", []) if isinstance(s, dict)],
            target_role,
        )

        # 3. 调 LLM 生成规划
        system = PLANNER_PROMPT.format(
            profile=json.dumps(profile, ensure_ascii=False),
            needs=json.dumps(needs, ensure_ascii=False),
            market=json.dumps(market, ensure_ascii=False)[:2000],
        )
        try:
            raw = await llm_call(self.llm or LLMClient(), "请生成", system=system, json_mode=True)
            plan = json.loads(raw)
        except Exception as e:
            logger.warning(f"planner LLM failed: {e}")
            plan = {
                "short_term": [{"title": "更新简历并投递 5 家公司", "duration": "2 周", "priority": "high"}],
                "mid_term": [{"title": "完成 1 个开源项目或认证", "duration": "3 个月", "milestone": "可演示作品"}],
                "long_term": [{"title": "成为领域专家或转型管理", "duration": "3 年", "outcome": "技术 leader"}],
                "learning_paths": [],
                "recommended_roles": [],
                "skill_gaps": [],
                "milestones": [],
            }

        # 4. 持久化
        record = {
            "id": str(uuid4()),
            "user_id": agent_input.user_id,
            "short_term": plan.get("short_term", []),
            "mid_term": plan.get("mid_term", []),
            "long_term": plan.get("long_term", []),
            "learning_paths": plan.get("learning_paths", []),
            "recommended_roles": plan.get("recommended_roles", []),
            "market_insights": market,
            "skill_gaps": plan.get("skill_gaps", []),
            "milestones": plan.get("milestones", []),
            "last_generated_at": datetime.utcnow().isoformat(),
        }
        try:
            from api.deps import get_supabase_admin
            supabase = get_supabase_admin()
            supabase.table("career_plans").upsert(record, on_conflict="user_id").execute()
        except Exception as e:
            logger.warning(f"failed to persist plan: {e}")

        # 5. 文本回复
        st = plan.get("short_term", [])
        return AgentOutput(
            agent_name=self.name,
            text=(
                f"🎯 短期({len(st)}项):\n" +
                "\n".join(f"  - {x.get('title')}" for x in st[:3]) + "\n\n"
                f"📅 长期目标:\n" +
                "\n".join(f"  - {x.get('title')}" for x in plan.get("long_term", [])[:2])
            ),
            artifacts=plan,
        )