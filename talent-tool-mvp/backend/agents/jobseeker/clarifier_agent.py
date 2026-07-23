"""Clarifier Agent - 用 LLM 多步推理 + 反思.

v6.0 EventBus: emits `profile.updated`, `needs.clarified`,
and `agent.completed` on success / `agent.failed` on error.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import uuid4

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.toolkit import llm_call
# v11.6 R2 — canonical extraction schema (single source of truth).
from agents.schemas import CLARIFIER_SYNTHESIS_SCHEMA
from eventbus import emit

logger = logging.getLogger("recruittech.agents.jobseeker.clarifier")


def _as_dict(raw: str | bytes, *, default: dict | None = None) -> dict:
    """Parse an LLM JSON string defensively into a dict.

    Local LLMs (Ollama) with ``response_format=json_object`` are not 100%
    reliable: they sometimes return a JSON array, a bare scalar, or prose.
    Without this guard the subsequent ``draft.get(...)`` calls raise
    ``AttributeError: list object has no attribute 'get'`` and crash the
    agent mid-run — the worst kind of demo failure.  Anything that is not a
    JSON object falls back to *default* (an empty dict), which keeps every
    downstream ``.get()`` safe and produces an explicit "信息不足" result
    instead of a traceback.
    """
    if default is None:
        default = {}
    if not raw:
        return default
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default
    return parsed if isinstance(parsed, dict) else default


def _load_reflective_system() -> str:
    """Load reflective system prompt. Falls back to default if config is absent."""
    from services.platform.config_service import get_prompt
    return get_prompt("clarifier", "system", default=REFLECTIVE_SYSTEM_DEFAULT)


REFLECTIVE_SYSTEM_DEFAULT = """你是求职者画像综合专家。

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
    return await llm_call(
        llm,
        json.dumps(all_data, ensure_ascii=False)[:8000],
        system=_load_reflective_system() + "\n\nSchema:\n" + CLARIFIER_SYNTHESIS_SCHEMA,
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
        run_id = str(uuid4())
        emit("agent.started", {"agent_name": self.name, "user_id": agent_input.user_id,
                               "run_id": run_id, "input_keys": list(ctx.keys())},
             source="agent.clarifier")

        # 1. 收集所有数据源
        all_data = {
            "profile": ctx.get("profile", {}),
            "journals": (ctx.get("journals") or [])[-10:],
            "conversations": (ctx.get("conversations") or [])[-20:],
            "emotion_history": (ctx.get("emotion_history") or [])[-30:],
        }

        # T2203: 把视频简历评分注入 context (如果有)
        video_summary = None
        profile_video = (all_data["profile"] or {}).get("video_resume_feedback") or {}
        scores_video = (all_data["profile"] or {}).get("_video_resume_scores") or {}
        if scores_video or profile_video:
            try:
                from services.jobseeker.video_resume_analyzer import (
                    VideoResumeAnalysis, VideoResumeScores, NonVerbalSignals,
                    summarize_for_clarifier,
                )
                analysis = VideoResumeAnalysis(
                    source_url=profile_video.get("source_url", ""),
                    video_metadata={},
                    frames_analyzed=int(profile_video.get("frames_analyzed", 0)),
                    scores=VideoResumeScores(**{k: float(v) for k, v in scores_video.items() if k != "overall"}),
                    non_verbal=NonVerbalSignals(),
                    strengths=list(profile_video.get("strengths") or []),
                    suggestions=list(profile_video.get("suggestions") or []),
                )
                if scores_video.get("overall") is not None:
                    analysis.scores.overall = float(scores_video["overall"])
                video_summary = summarize_for_clarifier(analysis)
                all_data["video_resume_summary"] = video_summary
                all_data["video_resume_scores"] = scores_video
            except Exception as e:  # noqa: BLE001
                logger.debug(f"video resume summary skipped: {e}")

        # 2. 第一步: 综合
        try:
            raw = await _llm_synthesize(self.llm or LLMClient(), all_data)
            draft = _as_dict(raw)
            if not draft:
                # json_mode returned nothing usable — surface as an explicit
                # error instead of silently producing an empty profile.
                draft = {"_error": "empty_llm_response"}
        except Exception as e:
            logger.warning(f"synthesize failed: {e}")
            draft = {"_error": str(e)}

        # 3. 第二步: 反思(可选)
        reflection = None
        if self.enable_reflection and "_error" not in draft:
            try:
                reflect_raw = await _llm_reflect(self.llm or LLMClient(), draft, all_data)
                reflection = _as_dict(reflect_raw)
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
        if video_summary:
            text += f"\n🎥 **视频简历**: {video_summary}\n"
        if draft.get("contradictions"):
            text += f"\n⚠️ 检测到 {len(draft['contradictions'])} 处冲突,请回顾确认。\n"

        if reflection:
            text += f"\n🤔 反思置信度: {int(reflection.get('confidence_after_reflection', 0.5) * 100)}%"

        # v6.0 EventBus: publish domain events
        try:
            completeness = (
                draft.get("info_completeness", {}).get("value", 0)
                if isinstance(draft.get("info_completeness"), dict) else 0
            )
            emit("profile.updated", {
                "user_id": agent_input.user_id,
                "candidate_id": ctx.get("candidate_id"),
                "fields": ["profile_synthesis", "explicit_needs", "implicit_needs"],
                "completeness": completeness,
                "source": "clarifier_agent",
            }, source="agent.clarifier", correlation_id=run_id)
            emit("needs.clarified", {
                "user_id": agent_input.user_id,
                "candidate_id": ctx.get("candidate_id"),
                "must_haves": record.get("must_haves", []),
                "deal_breakers": record.get("deal_breakers", []),
                "confidence": record.get("confidence_score", 0.5),
            }, source="agent.clarifier", correlation_id=run_id)
        except Exception as _e:
            logger.debug("eventbus publish failed: %s", _e)

        emit("agent.completed", {
            "agent_name": self.name,
            "user_id": agent_input.user_id,
            "run_id": run_id,
            "artifacts_count": len(draft),
        }, source="agent.clarifier", correlation_id=run_id)

        return AgentOutput(
            agent_name=self.name,
            text=text,
            artifacts={
                **draft,
                "reflection": reflection,
                "reasoning_chain": ["synthesize", "reflect"] if self.enable_reflection else ["synthesize"],
            },
        )


def record_user_correction(
    user_id: str,
    *,
    field_path: str,
    original_value: str,
    corrected_value: str,
    reason: str = "",
) -> dict:
    """v8.1 T3605 — 记录用户对画像的修正, 写回 Mem0 用于未来 learning.

    返回: 写回结果 + 供前端展示的 correction 对象.
    """
    correction = {
        "id": str(uuid4()),
        "user_id": user_id,
        "field_path": field_path,
        "original_value": original_value,
        "corrected_value": corrected_value,
        "reason": reason,
        "created_at": datetime.utcnow().isoformat(),
    }
    # 1. 写 DB
    try:
        from api.deps import get_supabase_admin
        supabase = get_supabase_admin()
        supabase.table("profile_corrections").insert(correction).execute()
    except Exception as e:
        logger.warning(f"persist correction failed: {e}")
    # 2. 写 Mem0 (best-effort)
    try:
        from services.memory import mem0_store
        if hasattr(mem0_store, "add_memory"):
            mem0_store.add_memory(
                user_id,
                text=(
                    f"用户修正画像字段 {field_path}: "
                    f"'{original_value}' -> '{corrected_value}'."
                    f" 原因: {reason or '未填'}"
                ),
                kind="profile_correction",
                metadata=correction,
            )
    except Exception as e:
        logger.debug("mem0 write failed: %s", e)
    return correction


def upvote_profile_field(user_id: str, *, field_path: str) -> dict:
    """用户对画像字段点赞 — 用于 AI 理解的我 面板."""
    return {
        "id": str(uuid4()),
        "user_id": user_id,
        "field_path": field_path,
        "kind": "upvote",
        "created_at": datetime.utcnow().isoformat(),
    }