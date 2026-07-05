"""Semantic Router — 用 embedding 语义相似度替代关键词路由.

设计哲学:
- ❌ 不再维护关键词表 (200+ if/elif)
- ✅ 把每个 agent 描述成"意图向量",LLM 生成 embedding
- ✅ 用户输入 → embedding → 余弦相似度 → top-k agents
- ✅ 模糊地带用 LLM 二判 (fallback)
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger("recruittech.agents.semantic_router")


# 用自然语言描述每个 agent 的"意图空间"(不写代码,让 LLM 理解)
AGENT_INTENT_DESCRIPTIONS = {
    "profile_agent": [
        "求职者介绍自己的基本信息",
        "上传或描述个人简历",
        "讨论学历、工作经历、技能",
        "询问我的资料是否齐全",
        "我想完善我的个人档案",
    ],
    "intake_agent": [
        "引导求职者一步步建立档案",
        "上传简历文件",
        "对话式建档",
    ],
    "daily_journal_agent": [
        "记录今天的工作内容",
        "写工作日记/周报",
        "汇报今天的任务和心得",
        "讨论今天的工作成果或困惑",
    ],
    "emotion_agent": [
        "表达高兴、难过、焦虑、愤怒",
        "倾诉心情和情绪",
        "我今天感觉很糟糕",
        "心情不好想聊聊",
        "感到压力和迷茫",
    ],
    "clarifier_agent": [
        "总结我的画像",
        "我到底想要什么样的工作",
        "整合我所有信息",
        "我的优势和需求是什么",
    ],
    "career_planner_agent": [
        "未来职业规划",
        "如何转行",
        "晋升路径",
        "学习什么技能",
        "长期职业目标",
    ],
    "persona_agent": [
        "HR 通用问题",
        "员工咨询制度",
        "离职流程、入职培训",
    ],
    "compliance_agent": [
        "上传营业执照",
        "验证企业资质",
        "资质审核",
    ],
    "vision_agent": [
        "公司的愿景和长远目标",
        "三年规划、五年战略",
        "企业使命",
    ],
    "talent_brief_agent": [
        "老板描述需要什么人",
        "人才画像",
        "招什么样的人",
    ],
    "job_spec_agent": [
        "岗位职责描述",
        "部门负责人细化 JD",
        "技能要求、工作内容",
    ],
    "policy_agent": [
        "考勤制度",
        "请假流程",
        "加班调休",
        "公司规章制度",
    ],
    "multi_party_agent": [
        "老板、HR、部门意见不一致",
        "多方协调",
        "跨部门决策",
    ],
    "employer_clarifier_agent": [
        "整合老板和部门的需求",
        "岗位的真实需求是什么",
    ],
    "hr_service_agent": [
        "我的假期还有几天",
        "晋升通道",
        "入职材料",
    ],
    "mutual_evaluator": [
        "面试互评",
        "双方打分",
        "要不要录用",
    ],
}


class SemanticRouter:
    """基于 embedding 相似度的语义路由."""

    def __init__(self, llm_client, agent_registry=None):
        self.llm = llm_client
        self.registry = agent_registry
        # 每个 agent 的"意图向量" = 它所有描述句子的平均 embedding
        self._intent_vectors: dict[str, np.ndarray] = {}
        self._intent_texts: dict[str, list[str]] = AGENT_INTENT_DESCRIPTIONS.copy()
        self._ready = False

    async def warmup(self):
        """预计算所有 agent 的意图向量(启动时调用)."""
        logger.info("Computing intent vectors for %d agents...", len(self._intent_texts))
        for agent_name, descriptions in self._intent_texts.items():
            vectors = []
            for desc in descriptions:
                emb = await self._embed(desc)
                if emb is not None:
                    vectors.append(np.array(emb))
            if vectors:
                # 用所有描述向量的平均作为 agent 的"代表向量"
                self._intent_vectors[agent_name] = np.mean(vectors, axis=0)
        self._ready = True
        logger.info("✅ Semantic router ready with %d intent vectors", len(self._intent_vectors))

    async def _embed(self, text: str) -> Optional[list[float]]:
        """调用 embedding 模型. mock 模式下返回 None,使用 fallback."""
        if self.llm and getattr(self.llm, "embed_fn", None):
            try:
                return await self.llm.embed_fn(text)
            except Exception as e:
                logger.warning(f"embedding failed: {e}")
        return None

    async def route(self, text: str, top_k: int = 3, threshold: float = 0.4) -> list[dict]:
        """语义路由: 返回 top-k 个最匹配的 agent.

        Returns:
            [{"agent": "xxx", "score": 0.85, "reasoning": "..."}]
        """
        if not self._ready:
            await self.warmup()

        # 1. 计算用户输入的 embedding
        user_vec = await self._embed(text)

        if user_vec is not None and self._intent_vectors:
            # 2. 真实 embedding: 余弦相似度排序
            user_arr = np.array(user_vec)
            scores = []
            for agent_name, agent_vec in self._intent_vectors.items():
                sim = self._cosine_similarity(user_arr, agent_vec)
                scores.append({"agent": agent_name, "score": float(sim)})
            scores.sort(key=lambda x: x["score"], reverse=True)

            # 过滤低分
            if scores[0]["score"] >= threshold:
                return scores[:top_k]

        # 3. Fallback: 让 LLM 理解意图并选择 agent
        return await self._llm_route(text, top_k)

    async def _llm_route(self, text: str, top_k: int) -> list[dict]:
        """用 LLM 做意图识别(自然语言理解,无规则)."""
        agents_desc = "\n".join(
            f"- {name}: {'; '.join(descs[:2])}"
            for name, descs in self._intent_texts.items()
        )

        prompt = f"""用户输入: "{text}"

可选 agent 及其职责:
{agents_desc}

请分析用户意图,选出最合适的 {top_k} 个 agent,并给出置信度(0~1)。
返回 JSON: [{{"agent": "agent_name", "score": 0.85, "reasoning": "为什么"}}]
只返回 JSON,不要其他内容。"""

        try:
            raw = await self.llm.call(
                [{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_cost_cents=5,
            )
            import json
            result = json.loads(raw)
            if isinstance(result, list):
                return result[:top_k]
            if isinstance(result, dict) and "agents" in result:
                return result["agents"][:top_k]
            # 兼容 {"result": [...]}
            if isinstance(result, dict) and "result" in result:
                return result["result"][:top_k]
            return [{"agent": "profile_agent", "score": 0.5, "reasoning": "fallback"}]
        except Exception as e:
            logger.warning(f"LLM routing failed: {e}")
            return [{"agent": "profile_agent", "score": 0.3, "reasoning": "默认 fallback"}]

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))


# 全局单例
_router: Optional[SemanticRouter] = None


async def get_semantic_router(llm_client=None, registry=None) -> SemanticRouter:
    global _router
    if _router is None:
        _router = SemanticRouter(llm_client=llm_client, agent_registry=registry)
        await _router.warmup()
    return _router