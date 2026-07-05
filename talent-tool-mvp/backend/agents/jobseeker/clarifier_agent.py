"""Clarifier Agent - 用 LLM 多步推理 + 反思."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import uuid4

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.toolkit import llm_call

logger = logging.getLogger("recruittech.agents.jobseeker.clarifier")


REFLECTIVE_SYSTEM = """你是求职者画像综合专家。

你的任务: 综合求职者所有来源的信息(画像/日记/对话/情绪),产出最准确的画像和需求。

工作流程:
1. **收集**: 把所有数据源组织成结构化视图
2. **识别冲突**: 不同来源说法不一致时,标记出来
3. **推断隐性**: 用户没说但从行为/语气中可推断的
4. **反思**: 再看一遍产出,问自己"我是不是过度解读了?"
5. **追问**: 信息缺口处生成引导式追问

输出 JSON,每个核心字段都包含:
- value: 你的结论
- reasoning: 为什么这么判断
- confidence: 0~1 信心分
- sources: 依据来源列表
"""


async def _llm_synthesize(llm: LLMClient, all_data: dict) -> dict:
    """第一步: 初步综合."""
    schema_hint = """
{
  "profile_synthesis": {
    "summary": {"value": "一句话", "reasoning": "..."},
    "explicit_skills": [{"value": "技能", "reasoning": "..."}],
    "implicit_traits": [{"value": "特质", "reasoning": "..."}],
    "value_orientation": [{"value": "价值观", "reasoning": "..."}],
    "career_interests": [{"value": "方向", "reasoning": "..."}]
  },
  "real_needs": {
    "explicit": [...],
    "implicit": [...],
    "must_haves": [...],
    "nice_to_haves": [...],
    "deal_breakers": [...]
  },
  "contradictions": [
    {"source_a": "...", "source_b": "...", "explanation": "..."}
  ],
  "follow_up_questions": [
    {"question": "...", "priority": "high/medium/low", "purpose": "为什么问"}
  ],
  "info_completeness": {"value": 0.0~1.0, "reasoning": "..."},
  "overall_confidence": 0.0~1.0
}
"""
    return await llm_call(
        llm,
        json.dumps(all_data, ensure_ascii=False)[:8000],
        system=REFLECTIVE_SYSTEM + "\n\nSchema:\n" + schema_hint,
        json_mode=True,
    )


async def _llm_reflect(llm: LLMClient, draft: dict, all_data: dict) -> dict:
    """第二步: 反思 — 我是不是过度解读?"""
    reflect_prompt = f"""现在反思你刚才的产出:

{draft}

原始数据:
{json.dumps(all_data, ensure_ascii=False)[:4000]}

请检查:
1. 是否有过度解读(把猜测当事实)?
2. 是否有遗漏的关键信息?
3. 是否有判断自相矛盾?

只返回 JSON:
{{
  "issues": ["问题1", "问题2"],
  "corrections": {{"字段": "修正值"}},
  "confidence_after_reflection": 0.0~1.0
}}
"""
    return await llm_call(llm, reflect_prompt, json_mode=True)


class ClarifierAgent(BaseAgent):
    """LLM-native 多步推理 + 反思 的澄清 Agent."""

    name = "clarifier_agent"
    description = "海量信息澄清 → 画像 + 真实需求 (1.5)"
    required_personas = ("jobseeker", "talent_partner", "admin")
    enable_reflection: bool = True

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        ctx = agent_input.context or {}

        # 1. 收集所有数据源
        all_data = {
            "profile": ctx.get("profile", {}),
            "journals": (ctx.get("journals") or [])[-10:],
            "conversations": (ctx.get("conversations") or [])[-20:],
            "emotion_history": (ctx.get("emotion_history") or [])[-30:],
        }

        # 2. 第一步: 综合
        try:
            raw = await _llm_synthesize(self.llm or LLMClient(), all_data)
            draft = json.loads(raw)
        except Exception as e:
            logger.warning(f"synthesize failed: {e}")
            draft = {"_error": str(e)}

        # 3. 第二步: 反思(可选)
        reflection = None
        if self.enable_reflection and "_error" not in draft:
            try:
                reflect_raw = await _llm_reflect(self.llm or LLMClient(), draft, all_data)
                reflection = json.loads(reflect_raw)
                # 把反思结果合并
                if reflection.get("corrections"):
                    for k, v in reflection["corrections"].items():
                        draft[k] = v
            except Exception as e:
                logger.warning(f"reflect failed: {e}")

        # 4. 持久化
        record = {
            "id": str(uuid4()),
            "user_id": agent_input.user_id,
            "candidate_id": ctx.get("candidate_id"),
            "profile_synthesis": draft.get("profile_synthesis", {}),
            "explicit_needs": draft.get("real_needs", {}).get("explicit", []),
            "implicit_needs": draft.get("real_needs", {}).get("implicit", []),
            "must_haves": draft.get("real_needs", {}).get("must_haves", []),
            "nice_to_haves": draft.get("real_needs", {}).get("nice_to_haves", []),
            "deal_breakers": draft.get("real_needs", {}).get("deal_breakers", []),
            "conflict_flags": draft.get("contradictions", []),
            "follow_up_questions": draft.get("follow_up_questions", []),
            "confidence_score": draft.get("overall_confidence", 0.5),
            "info_completeness": draft.get("info_completeness", {}).get("value", 0) if isinstance(draft.get("info_completeness"), dict) else 0,
            "last_synthesized_at": datetime.utcnow().isoformat(),
        }
        try:
            from api.deps import get_supabase_admin
            supabase = get_supabase_admin()
            supabase.table("candidate_clarifications").upsert(
                record, on_conflict="user_id"
            ).execute()
        except Exception as e:
            logger.warning(f"persist failed: {e}")

        # 5. 组装用户可见的回复
        ps = draft.get("profile_synthesis", {})
        summary = ps.get("summary", {})
        if isinstance(summary, dict):
            summary = summary.get("value", "信息不足")
        elif isinstance(summary, str):
            pass
        else:
            summary = "信息不足"

        needs = draft.get("real_needs", {})
        text = (
            f"📌 **你的画像**: {summary}\n\n"
            f"✅ 显性需求: {' / '.join(str(n) for n in needs.get('explicit', [])[:3]) or '暂未提取'}\n"
            f"🔍 推断需求: {' / '.join(str(n) for n in needs.get('implicit', [])[:3]) or '暂未提取'}\n"
        )
        if draft.get("contradictions"):
            text += f"\n⚠️ 检测到 {len(draft['contradictions'])} 处冲突,请回顾确认。\n"

        if reflection:
            text += f"\n🤔 反思置信度: {int(reflection.get('confidence_after_reflection', 0.5) * 100)}%"

        return AgentOutput(
            agent_name=self.name,
            text=text,
            artifacts={
                **draft,
                "reflection": reflection,
                "reasoning_chain": ["synthesize", "reflect"] if self.enable_reflection else ["synthesize"],
            },
        )