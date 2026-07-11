"""Career Planner Agent - 职业规划师/顾问.

需求 1.6: 多层次职业规划,基于画像+真实需求+市场行情.

T607 升级:
    - fetch_market_insights 改用 providers.job_market (真实 API + 自动 mock 降级)
    - 新增 fetch_learning_resources (services.learning_resources 聚合)
    - 新增 _init_plan_tracker (services.plan_tracker 落地)
"""
from __future__ import annotations

import asyncio
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


async def fetch_market_insights(
    skills: list[str],
    target_role: str | None,
    *,
    city: str = "上海",
) -> dict:
    """拉取市场行情 (T607).

    数据源:
        - 招聘市场 provider (boss / lagou / linkedin / adzuna / mock)
        - 真实 API 失败时自动降级到 mock,不会阻塞业务

    返回结构 (供下游 LLM 提示词使用):
        {
            "salary_trends": [{period, median_k, p25_k, p75_k, sample_size, currency}],
            "hot_skills":    [{skill, demand_score, job_count, growth_pct}],
            "sample_jobs":   [{title, company, city, salary_min_k, salary_max_k, ...}],
            "provider":      "boss" / "lagou" / "linkedin" / "adzuna" / "mock",
        }
    """
    from providers.job_market import get_job_market_provider
    from providers.job_market.types import SalaryPoint, SkillDemand, JobPosting

    role = target_role or (skills[0] if skills else "Python 后端")
    top_skills = skills[:3] if skills else ["Python", "FastAPI", "PostgreSQL"]

    provider = get_job_market_provider()
    provider_name = getattr(provider, "provider_name", "unknown")

    # 并行拉 salary trend / hot skills / sample jobs
    salary_task = provider.get_salary_trend(role, city, months=12)
    hot_task = provider.get_hot_skills(role, limit=15)
    sample_task = provider.search_jobs(role, city=city, page_size=5)

    salary_trends, hot_skills, sample_jobs = await asyncio.gather(
        salary_task, hot_task, sample_task,
        return_exceptions=True,
    )

    def _unwrap(x, default):
        return x if not isinstance(x, Exception) else default

    return {
        "salary_trends": _unwrap(salary_trends, []),
        "hot_skills": _unwrap(hot_skills, []),
        "sample_jobs": _unwrap(sample_jobs, []),
        "provider": provider_name,
    }


def _serialize_market_insights(insights: dict) -> dict:
    """把 dataclass 序列化成 dict, 方便 LLM 提示词拼接."""
    from dataclasses import asdict, is_dataclass

    def _conv(x):
        if is_dataclass(x):
            return asdict(x)
        if isinstance(x, list):
            return [_conv(i) for i in x]
        return x

    return {k: _conv(v) for k, v in insights.items()}


async def fetch_learning_resources(
    skill_gaps: list[str],
    *,
    overall_limit: int = 15,
) -> dict:
    """拉取学习资源推荐 (T607)."""
    from services.learning_resources import get_learning_resources_service

    if not skill_gaps:
        return {"gap_skills": [], "items": []}
    svc = get_learning_resources_service()
    rows = await svc.recommend(skill_gaps, overall_limit=overall_limit)
    return {
        "gap_skills": skill_gaps,
        "items": [
            {
                "title": r.title,
                "provider": r.provider,
                "url": r.url,
                "duration_hours": r.duration_hours,
                "level": r.level,
                "rating": r.rating,
                "skill_tags": r.skill_tags,
                "price": r.price,
                "language": r.language,
                "source": r.source,
            }
            for r in rows
        ],
    }


def _init_plan_tracker(user_id: str, plan: dict) -> None:
    """把生成的 plan 落地到 plan_tracker."""
    from services.plan_tracker import get_plan_tracker

    try:
        svc = get_plan_tracker()
        svc.create_plan(user_id, plan_data=plan)
    except Exception as exc:  # pragma: no cover - 兜底
        logger.warning("plan_tracker init failed: %s", exc)


def _merge_learning_paths(
    existing: list[dict],
    real_items: list[dict],
    *,
    max_per_topic: int = 3,
) -> list[dict]:
    """合并 LLM 生成的 learning_paths 和 services.learning_resources 真实数据.

    策略: 保留 LLM 给的 topic 分类,用真实资源替换 resources 列表.
    """
    # 按 topic 索引真实资源
    bucket: dict[str, list[dict]] = {}
    for item in real_items:
        for tag in item.get("skill_tags", []) or []:
            bucket.setdefault(tag.lower(), []).append(item)

    # 给现有 topic 填充
    out: list[dict] = []
    seen_topics: set[str] = set()
    for entry in existing or []:
        if not isinstance(entry, dict):
            continue
        topic = (entry.get("topic") or "").strip()
        if not topic:
            continue
        seen_topics.add(topic.lower())
        # 优先用 topic 命中,否则用原 LLM 资源
        matched = bucket.get(topic.lower(), [])
        new_resources = matched[:max_per_topic] or entry.get("resources", [])
        out.append({
            "topic": topic,
            "resources": new_resources,
            "source": "real" if matched else "llm",
        })

    # 补充 LLM 没给、但真实数据有的 topic
    for topic, items in bucket.items():
        if topic in seen_topics:
            continue
        out.append({
            "topic": topic,
            "resources": items[:max_per_topic],
            "source": "real",
        })

    # 兜底: 都没有时返回全部真实数据打包成单一 topic
    if not out and real_items:
        out.append({
            "topic": "推荐学习资源",
            "resources": real_items[:max_per_topic],
            "source": "real",
        })
    return out


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

        # 2. 拉取市场行情 (T607: 用 providers.job_market)
        market = await fetch_market_insights(
            [s.get("name") for s in profile.get("skills", []) if isinstance(s, dict)],
            target_role,
            city=ctx.get("city", "上海"),
        )

        # 2b. 拉取学习资源推荐 (T607) — 用 profile 里的 top skills 作为兜底,
        # LLM 生成 plan 后再用 skill_gaps 重新覆盖
        profile_skill_names = [
            s.get("name") for s in profile.get("skills", [])
            if isinstance(s, dict) and s.get("name")
        ][:3]
        learning = await fetch_learning_resources(profile_skill_names, overall_limit=10)

        # 3. 调 LLM 生成规划
        system = PLANNER_PROMPT.format(
            profile=json.dumps(profile, ensure_ascii=False),
            needs=json.dumps(needs, ensure_ascii=False),
            market=json.dumps(_serialize_market_insights(market), ensure_ascii=False)[:2000],
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

        # 4. 用真实 gap skills 重新拉学习资源 + 合并到 plan
        skill_gaps = plan.get("skill_gaps", []) or []
        gap_skill_names = [
            g.get("skill") for g in skill_gaps if isinstance(g, dict) and g.get("skill")
        ] if isinstance(skill_gaps, list) else []
        if gap_skill_names:
            learning = await fetch_learning_resources(gap_skill_names, overall_limit=10)
        plan["learning_paths"] = _merge_learning_paths(
            plan.get("learning_paths", []), learning["items"],
        )

        # 4b. 持久化
        record = {
            "id": str(uuid4()),
            "user_id": agent_input.user_id,
            "short_term": plan.get("short_term", []),
            "mid_term": plan.get("mid_term", []),
            "long_term": plan.get("long_term", []),
            "learning_paths": plan.get("learning_paths", []),
            "recommended_roles": plan.get("recommended_roles", []),
            "market_insights": _serialize_market_insights(market),
            "market_provider": market.get("provider"),
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

        # 4c. 初始化 plan_tracker (供后续 checkin / adjust 使用)
        _init_plan_tracker(agent_input.user_id, plan)

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