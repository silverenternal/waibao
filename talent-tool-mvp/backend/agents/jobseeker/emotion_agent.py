"""Emotion Agent - 纯 LLM 实现,删除所有词典/正则."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import uuid4

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.llm_extractor import detect_emotion

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