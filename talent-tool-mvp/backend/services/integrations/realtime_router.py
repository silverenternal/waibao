"""Realtime Router — 升级为 Semantic Router.

不再维护关键词列表。改为:
1. embedding 相似度 (主)
2. LLM 深度意图理解 (兜底)
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("recruittech.services.realtime_router")


# 这些描述会被 semantic_router 用 embedding 索引
AGENT_DESCRIPTIONS_FALLBACK = {
    "profile_agent": "求职者介绍自己、讨论个人基本信息、修改档案",
    "daily_journal_agent": "记录今天的工作内容、写工作日记、汇报任务",
    "emotion_agent": "表达情绪、倾诉心情、焦虑难过、压力",
    "clarifier_agent": "整合我的所有信息、生成画像、找出真实需求",
    "career_planner_agent": "职业规划、未来方向、转行、学习路径",
    "persona_agent": "HR 通用问题、员工咨询",
    "compliance_agent": "上传营业执照、资质验证",
    "vision_agent": "公司愿景、长远目标、战略",
    "talent_brief_agent": "描述需要什么样的人才",
    "job_spec_agent": "细化岗位职责、JD 内容",
    "policy_agent": "考勤、请假、加班、规章制度",
    "multi_party_agent": "老板 HR 部门负责人意见冲突",
    "employer_clarifier_agent": "整合用人方需求、生成岗位画像",
    "hr_service_agent": "入职、离职、培训、晋升",
    "mutual_evaluator": "面试互评、双方打分",
}


class RealtimeRouter:
    """优先用 semantic_router;embedding 不可用时降级到 LLM 意图理解."""

    def __init__(self, registry=None, llm_client=None):
        self.registry = registry
        self.llm = llm_client
        self._semantic = None

    async def _get_semantic(self):
        if self._semantic is None:
            from agents.semantic_router import get_semantic_router
            self._semantic = await get_semantic_router(
                llm_client=self.llm,
                registry=self.registry,
            )
        return self._semantic

    async def route_async(self, text: str, persona: str = "jobseeker") -> str:
        """异步路由(优先 embedding,失败降级)."""
        try:
            semantic = await self._get_semantic()
            results = await semantic.route(text, top_k=1, threshold=0.3)
            if results:
                agent_name = results[0]["agent"]
                if self.registry and self.registry.get(agent_name):
                    logger.info(f"[router] '{text[:30]}' → {agent_name} (semantic, score={results[0]['score']:.2f})")
                    return agent_name
        except Exception as e:
            logger.warning(f"semantic router failed: {e}")

        # fallback: LLM 意图理解
        return await self._llm_route(text, persona)

    async def _llm_route(self, text: str, persona: str) -> str:
        """用 LLM 深度理解意图."""
        from agents.llm_extractor import understand_intent
        result = await understand_intent(
            self.llm,
            text,
            AGENT_DESCRIPTIONS_FALLBACK,
        )
        agent = result.get("best_agent", "profile_agent")
        if self.registry and self.registry.get(agent) is None:
            agent = "profile_agent"
        logger.info(f"[router] '{text[:30]}' → {agent} (LLM intent, reasoning={result.get('reasoning', '')[:80]})")
        return agent

    # 同步 API (向后兼容): 直接调 async
    def route(self, text: str, persona: str = "jobseeker") -> str:
        """同步包装 — 实际开发用 route_async()."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在 async 上下文中,直接返回第一个候选
                return self._sync_emergency_route(text, persona)
            return loop.run_until_complete(self.route_async(text, persona))
        except RuntimeError:
            return asyncio.run(self.route_async(text, persona))

    def _sync_emergency_route(self, text: str, persona: str) -> str:
        """异步上下文里的兜底 — 不依赖 embedding, 直接 LLM."""
        # 简单关键词作为最后兜底(避免循环)
        keywords = {
            "emotion_agent": ["开心", "难过", "焦虑", "崩溃", "压力", "心情"],
            "daily_journal_agent": ["今天", "日记", "周报", "记录"],
            "career_planner_agent": ["规划", "未来", "转行", "晋升"],
            "policy_agent": ["请假", "考勤", "加班", "调休", "制度"],
            "clarifier_agent": ["我的画像", "总结我", "我的需求"],
        }
        for agent, kws in keywords.items():
            if any(kw in text for kw in kws):
                if self.registry and self.registry.get(agent):
                    return agent
        return "profile_agent"