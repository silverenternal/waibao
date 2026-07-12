"""用人单位 Persona Agent - 真诚HR的人格基底.

需求 2.1 / 2.9: 真诚HR,老板得力助手; 员工全生命周期服务.

增强 (T703):
    - run() 时读 persona_memory → 注入 system prompt
    - 自动从用户输入里推断偏好 → upsert 到 persona_prefs
    - escalation 触发工单 (T704)
"""
from __future__ import annotations

import json
import logging

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.toolkit import llm_call
from eventbus import emit
from services.persona_memory import (
    render_prefs_for_prompt,
    get_prefs,
    infer_prefs_from_text,
    MIN_CONFIDENCE,
)

logger = logging.getLogger("recruittech.agents.employer.persona")

HR_PERSONA_SYSTEM = """你是用人单位的"真诚HR"人格化身。

性格:
- 专业、有同理心、不卑不亢
- 主动思考公司长期利益,而非短期凑数
- 对老板敢说真话,对求职者保持尊重
- 严格遵守劳动法和候选人隐私

回答时:
1. 先复述确认你理解的问题
2. 再给出方案/建议
3. 列出风险点和边界
4. 必要时建议联系直线 HR(涉及个人隐私/纪律问题)
"""

# 敏感问题关键词 (T704 升级人工)
SENSITIVE_KEYWORDS = [
    "工资条", "个税", "社保", "开除", "解雇", "辞退",
    "性骚扰", "歧视", "霸凌", "欺凌",
    "拖欠工资", "降薪", "加班费",
    "工伤", "不想活了", "想轻生", "自残",
    "仲裁", "诉讼",
]


def _is_sensitive(text: str) -> bool:
    return any(kw in text for kw in SENSITIVE_KEYWORDS)


class PersonaAgent(BaseAgent):
    name = "persona_agent"
    description = "真诚HR人格基底 + 员工全生命周期 (2.1 / 2.9)"
    required_personas = ("hr", "boss", "admin", "dept_head")

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        text = agent_input.text
        ctx = agent_input.context or {}
        user_id = agent_input.user_id
        organisation_id = ctx.get("organisation_id")

        # ---- 1. 敏感问题 → 升级人工 + 建工单 (T704) ----
        sensitive = _is_sensitive(text)
        escalation = None
        if sensitive:
            escalation = await self._maybe_escalate(ctx, user_id, text)

        # ---- 2. 注入 persona 偏好 (T703) ----
        supabase = ctx.get("supabase")
        prefs_block = ""
        if supabase is not None:
            try:
                prefs = await get_prefs(supabase, user_id, organisation_id)
                prefs_block = render_prefs_for_prompt(prefs)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"persona_agent load prefs failed: {e}")

        system = HR_PERSONA_SYSTEM
        if prefs_block:
            system += "\n\n" + prefs_block

        # ---- 3. LLM 调用 ----
        raw = await llm_call(self.llm or LLMClient(), text, system=system)

        # ---- 4. 自动学习偏好 (best-effort, 非敏感话题) ----
        learned: list[dict] = []
        if supabase is not None and not sensitive:
            try:
                learned = await infer_prefs_from_text(
                    supabase, user_id, organisation_id, text, llm=self.llm
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"persona_agent infer prefs failed: {e}")

        artifacts = {
            "persona": "sincere_hr",
            "sensitive_detected": sensitive,
            "prefs_count": len(prefs_block.split("\n")) - 1 if prefs_block else 0,
            "prefs_learned": len(learned),
            "prefs_min_confidence": MIN_CONFIDENCE,
        }
        if escalation:
            artifacts["escalation"] = escalation
        if learned:
            artifacts["prefs_learned_rows"] = learned

        response_text = raw
        if escalation and escalation.get("ticket_id"):
            tid = str(escalation["ticket_id"])[:8]
            response_text += (
                f"\n\n---\n我已为你创建一个保密工单 (#{tid}),"
                "HR/HRBP 会在工作时间内联系你。"
            )

        # v6.0 EventBus — publish ticket.created on escalation
        try:
            if escalation and escalation.get("ticket_id"):
                emit("ticket.created", {
                    "ticket_id": str(escalation["ticket_id"]),
                    "employer_id": user_id,
                    "severity": "high",
                    "category": "persona_escalation",
                    "summary": escalation.get("reason", "persona agent escalation"),
                }, source="agent.persona")
        except Exception as _e:
            logger.debug("eventbus publish failed: %s", _e)

        return AgentOutput(
            agent_name=self.name,
            text=response_text,
            artifacts=artifacts,
        )

    async def _maybe_escalate(self, ctx: dict, user_id: str, text: str) -> dict | None:
        """敏感问题 → 创建工单 + 返回 ticket 信息 (T704)。"""
        supabase = ctx.get("supabase")
        organisation_id = ctx.get("organisation_id")
        if supabase is None:
            return {"escalated": False, "reason": "no_supabase"}

        # 优先级 (粗暴兜底)
        priority = "high"
        if any(w in text for w in ["不想活了", "想轻生", "自残", "工伤"]):
            priority = "urgent"
        elif any(w in text for w in ["性骚扰", "歧视", "霸凌", "拖欠工资", "解雇"]):
            priority = "urgent"

        department = ctx.get("department") or "general"
        role = ctx.get("asker_role") or "employee"

        try:
            from services.ticket_service import create_ticket

            ticket = create_ticket(
                supabase,
                user_id=user_id,
                auto_create=True,
                title=f"[敏感问题] {text[:50]}",
                description=text,
                priority=priority,
                category="complaint",
                organisation_id=organisation_id,
                metadata={
                    "source": "persona_agent",
                    "agent_name": "persona_agent",
                    "trigger": "sensitive_keyword",
                    "asker_role": role,
                    "department": department,
                    "suggested_hrbp": True,
                },
                tags=["auto", "sensitive", "needs_hrbp"],
            )
            return {
                "escalated": True,
                "ticket_id": ticket.id if hasattr(ticket, "id") else ticket.get("id", ""),
                "ticket_no": getattr(ticket, "no", None) or ticket.get("no"),
                "priority": priority,
                "department": department,
                "suggested_hrbp": True,
            }
        except Exception as e:  # noqa: BLE001
            logger.warning(f"persona_agent escalate failed: {e}")
            return {"escalated": False, "reason": str(e)}