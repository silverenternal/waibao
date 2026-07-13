"""Emotion Agent - 纯 LLM 实现,删除所有词典/正则.

v6.0 EventBus: emits `emotion.detected`, `emotion.risk` (when risk
level >= mild).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import uuid4

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.llm_extractor import detect_emotion
from eventbus import emit

logger = logging.getLogger("recruittech.agents.jobseeker.emotion")


SYSTEM_PROMPT = """你是用户的情感智能助手。

回应风格:
1. 先共情(理解对方感受)
2. 不评判
3. 必要时温和地把话题引导回职业/工作
4. 检测到心理风险时,温和建议联系专业人士

注意:
- 不要长篇大论
- 不要用太多emoji
- 像朋友聊天,不像心理咨询报告
"""


class EmotionAgent(BaseAgent):
    """LLM-native 情绪识别 + 共情回应."""

    name = "emotion_agent"
    description = "情感接收 + 共情回应(1.4)"
    required_personas = ("jobseeker", "talent_partner", "admin")

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        text = agent_input.text
        ctx = agent_input.context or {}

        # 从 memory 取最近的对话上下文(增强情绪连贯性)
        history = ctx.get("recent_conversations", [])

        # 1. LLM 情绪分析(一次调用同时拿分析+回应)
        result = await detect_emotion(self.llm or LLMClient(), text, history)

        # 2. 写情绪时间线(只有有意义的情绪才记)
        risk = result.get("risk_level", "none")
        if risk in ("mild", "moderate", "severe") or result.get("primary_emotion") != "neutral":
            record = {
                "id": str(uuid4()),
                "user_id": agent_input.user_id,
                "recorded_at": datetime.utcnow().isoformat(),
                "primary_emotion": result.get("primary_emotion", "neutral"),
                "intensity": max(
                    (e.get("intensity", 0) for e in result.get("emotions", [])),
                    default=0.0,
                ),
                "sentiment": self._sentiment_from_emotions(result.get("emotions", [])),
                "trigger_text": text[:200],
                "context": ctx,
                "needs_attention": risk in ("moderate", "severe"),
            }
            try:
                from api.deps import get_supabase_admin
                supabase = get_supabase_admin()
                supabase.table("emotion_timeline").insert(record).execute()
            except Exception as e:
                logger.warning(f"persist emotion failed: {e}")

        # 3. 高风险推送给管理员
        if risk in ("moderate", "severe"):
            try:
                from services.notify import push
                await push(
                    channel="dingtalk",
                    user_id="hr_team",
                    title="求职者情绪告警",
                    content=f"用户 {agent_input.user_id}: {result.get('primary_emotion')} (风险 {risk})",
                )
            except Exception:
                pass

        # 4. 风险高时附加建议
        response_text = result.get("response", "我在听。")
        if risk == "severe":
            response_text += (
                "\n\n💙 我注意到你现在的状态不太好,如果你觉得很难受,建议联系专业心理咨询。"
                "全国24小时心理援助热线: 400-161-9995。"
            )

        # v8.1 T3604 — 高风险自动触发关怀 workflow
        intensity = max(
            (e.get("intensity", 0) for e in result.get("emotions", [])),
            default=0.0,
        )
        care_ticket_id: str | None = None
        if risk in ("mild", "moderate", "severe"):
            try:
                from services.jobseeker.emotion_care import get_emotion_care_service

                care = get_emotion_care_service()
                ticket = care.trigger_care(
                    agent_input.user_id,
                    risk_level=risk,
                    primary_emotion=result.get("primary_emotion", "neutral"),
                    trigger_text=text,
                    intensity=intensity,
                )
                care_ticket_id = ticket.id
                # 用关怀 ticket 里的资源替换 response
                resources = care.list_actions(ticket.id)
                if resources:
                    first_res = next(
                        (a for a in resources if a.action_type == "send_resource"),
                        None,
                    )
                    if first_res:
                        response_text += (
                            f"\n\n🌱 我给你准备了一个小资源: 《{first_res.payload.get('title')}》"
                            f" — {first_res.payload.get('url')}"
                        )
            except Exception as _e:
                logger.debug("emotion care workflow failed: %s", _e)

        # v6.0 EventBus — publish domain events
        try:
            intensity = max(
                (e.get("intensity", 0) for e in result.get("emotions", [])),
                default=0.0,
            )
            emit("emotion.detected", {
                "user_id": agent_input.user_id,
                "primary_emotion": result.get("primary_emotion", "neutral"),
                "intensity": intensity,
                "sentiment": self._sentiment_from_emotions(result.get("emotions", [])),
                "evidence": [e.get("evidence") for e in result.get("emotions", [])][:3],
            }, source="agent.emotion")
            if risk in ("mild", "moderate", "severe"):
                emit("emotion.risk", {
                    "user_id": agent_input.user_id,
                    "risk_level": risk,
                    "primary_emotion": result.get("primary_emotion", "neutral"),
                    "intensity": intensity,
                    "recommended_action": "page_hr" if risk in ("moderate", "severe") else "log",
                }, source="agent.emotion")
        except Exception as _e:
            logger.debug("eventbus publish failed: %s", _e)

        return AgentOutput(
            agent_name=self.name,
            text=response_text,
            artifacts={
                "primary_emotion": result.get("primary_emotion"),
                "emotions": result.get("emotions"),
                "complexity": result.get("complexity"),
                "underlying_need": result.get("underlying_need"),
                "risk_level": risk,
                "response_tone": result.get("recommended_response_tone"),
                "needs_attention": risk in ("moderate", "severe"),
                "reasoning": {e.get("name"): e.get("evidence") for e in result.get("emotions", [])},
                "care_ticket_id": care_ticket_id,
            },
        )

    @staticmethod
    def _sentiment_from_emotions(emotions: list) -> float:
        """从情绪列表估计 sentiment."""
        positive = {"joy", "hope", "excitement", "gratitude", "relief", "pride"}
        negative = {"sadness", "anger", "anxiety", "fear", "frustration", "hopelessness"}
        score = 0.0
        for e in emotions:
            name = e.get("name", "")
            intensity = e.get("intensity", 0)
            if name in positive:
                score += intensity
            elif name in negative:
                score -= intensity
        return max(-1.0, min(1.0, score))