"""HR Service Agent - 员工全生命周期.

需求 2.9: 智能体成为用人方的 HR,覆盖招聘→入职→培训→绩效→晋升→离职.

增强 (T207):
    当识别到敏感问题 (薪资投诉 / 歧视 / 心理危机 / 性骚扰 / 离职纠纷 等)
    时,自动调用 ticket_service.create_ticket 创建工单,交给 HR 处理。
    智能体回复中会附上工单号让员工可以跟进。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from agents.runtime import AgentInput, AgentOutput, BaseAgent, LLMClient
from agents.toolkit import llm_call
from eventbus import emit

logger = logging.getLogger("recruittech.agents.employer.hr_service")

HR_SERVICE_PROMPT = """你是企业 HR 全生命周期助手。

员工问题: "{text}"
当前阶段: {stage}

请根据阶段给出回答。覆盖范围:
- 招聘: 进度查询、面试安排
- 入职: 流程、材料清单、入职培训
- 培训: 课程推荐、认证路径
- 绩效: 评估周期、自我评估模板
- 晋升: 通道、流程、晋升答辩
- 离职: 流程、交接清单、离职证明

涉及个人隐私/纪律问题时,建议联系直线 HR。

特别提示: 以下问题属于"敏感问题",必须 create_ticket=true 并 escalate_to_human=true:
- 薪资争议、拖欠、降薪
- 性骚扰、歧视、霸凌
- 心理危机、想轻生
- 违纪处分、解雇纠纷
- 工作环境安全 / 工伤
- 涉及法律纠纷

输出 JSON:
{{
  "stage": "recruiting/onboarding/training/performance/promotion/offboarding/general",
  "answer": "具体回答",
  "action_items": ["行动项"],
  "create_ticket": true/false,
  "ticket_category": "hr/policy/payroll/benefits/training/complaint/other (仅 create_ticket=true 时填)",
  "ticket_priority": "low/normal/high/urgent (仅 create_ticket=true 时填)",
  "escalate_to_human": true/false
}}
"""


STAGE_KEYWORDS = {
    "recruiting": ["面试", "招聘", "投递", "流程"],
    "onboarding": ["入职", "报到", "第一天", "材料"],
    "training": ["培训", "学习", "课程", "认证"],
    "performance": ["绩效", "考核", "评估", "KPI"],
    "promotion": ["晋升", "提拔", "升职", "晋级"],
    "offboarding": ["离职", "辞职", "交接", "last day"],
}

# 敏感问题关键词 (用于本地兜底,避免 LLM 失手漏掉)
SENSITIVE_KEYWORDS: dict[str, str] = {
    # 薪资 / 拖欠
    "拖欠工资": "urgent",
    "降薪": "high",
    "不发工资": "urgent",
    "工资纠纷": "high",
    "加班费": "normal",
    # 歧视 / 骚扰
    "性骚扰": "urgent",
    "歧视": "high",
    "霸凌": "high",
    "欺凌": "high",
    # 心理危机
    "不想活了": "urgent",
    "想轻生": "urgent",
    "自残": "urgent",
    "抑郁": "high",
    "崩溃": "high",
    # 处分 / 纠纷
    "解雇": "urgent",
    "开除": "urgent",
    "辞退": "urgent",
    "违纪处分": "high",
    "仲裁": "high",
    "诉讼": "high",
    # 安全
    "工伤": "urgent",
    "工作场所安全": "high",
}


def _detect_stage(text: str) -> str:
    text_lower = text.lower()
    for stage, kws in STAGE_KEYWORDS.items():
        if any(kw in text for kw in kws):
            return stage
    return "general"


def _detect_sensitive(text: str) -> tuple[bool, str, str]:
    """本地兜底检测敏感问题.

    Returns: (is_sensitive, category, priority)
    """
    text_lower = text.lower()
    # 心理危机 → urgent
    crisis_words = ["不想活了", "想轻生", "自杀", "自残"]
    for w in crisis_words:
        if w in text:
            return True, "complaint", "urgent"
    # 骚扰 / 歧视
    harassment_words = ["性骚扰", "歧视", "霸凌", "欺凌"]
    for w in harassment_words:
        if w in text:
            return True, "complaint", "urgent"
    # 薪资
    payroll_words = ["拖欠工资", "不发工资", "降薪", "工资纠纷", "加班费"]
    for w in payroll_words:
        if w in text:
            return True, "payroll", "high"
    # 处分
    discipline_words = ["解雇", "开除", "辞退", "违纪处分", "仲裁", "诉讼"]
    for w in discipline_words:
        if w in text:
            return True, "complaint", "urgent"
    # 安全
    safety_words = ["工伤", "工作场所安全"]
    for w in safety_words:
        if w in text:
            return True, "hr", "urgent"
    return False, "hr", "normal"


def _safe_create_ticket(supabase: Any, user_id: str, **kwargs) -> dict | None:
    """安全创建工单 — 失败不抛,只记日志."""
    try:
        from services.ticket_service import create_ticket

        ticket = create_ticket(supabase, user_id=user_id, auto_create=True, **kwargs)
        return ticket.to_dict()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"hr_service_agent: 自动建工单失败: {exc}")
        return None


class HRServiceAgent(BaseAgent):
    name = "hr_service_agent"
    description = "员工全生命周期 HR 服务 (2.9)"
    required_personas = ("hr", "boss", "dept_head", "admin")

    async def _handle(self, agent_input: AgentInput) -> AgentOutput:
        text = agent_input.text
        ctx = agent_input.context or {}
        stage = ctx.get("stage") or _detect_stage(text)
        user_id = agent_input.user_id

        # 1. 本地兜底敏感检测 (LLM 失败时也保证不漏)
        local_sensitive, local_category, local_priority = _detect_sensitive(text)
        local_ticket_info: dict | None = None
        if local_sensitive:
            # 尝试创建工单 (依赖 supabase client; 没有就 skip)
            supabase = ctx.get("supabase")
            organisation_id = ctx.get("organisation_id")
            if supabase is not None:
                local_ticket_info = _safe_create_ticket(
                    supabase,
                    user_id,
                    title=f"[敏感问题] {text[:50]}",
                    description=text,
                    priority=local_priority,
                    category=local_category,
                    organisation_id=organisation_id,
                    metadata={
                        "source": "agent",
                        "agent_name": self.name,
                        "trigger": "sensitive_keyword",
                        "matched_keyword": text,
                    },
                    tags=["auto", "sensitive"],
                )

        # 2. LLM 调用
        try:
            raw = await llm_call(
                self.llm or LLMClient(),
                HR_SERVICE_PROMPT.format(text=text, stage=stage),
                system="你是温情专业的 HR 助手。",
                json_mode=True,
            )
            result = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"hr_service_agent LLM 调用失败: {exc}")
            result = {
                "stage": stage,
                "answer": text[:200] or "我在,有什么需要帮助?",
                "action_items": [],
                "create_ticket": local_sensitive,
                "ticket_category": local_category if local_sensitive else "hr",
                "ticket_priority": local_priority if local_sensitive else "normal",
                "escalate_to_human": local_sensitive,
            }

        # 3. 如果 LLM 判断需要建工单但本地没建出来 → 这里补建
        ticket_info = local_ticket_info
        if result.get("create_ticket") and ticket_info is None:
            supabase = ctx.get("supabase")
            organisation_id = ctx.get("organisation_id")
            if supabase is not None:
                ticket_info = _safe_create_ticket(
                    supabase,
                    user_id,
                    title=f"[自动建单] {text[:50]}",
                    description=text,
                    priority=result.get("ticket_priority", "normal"),
                    category=result.get("ticket_category", "hr"),
                    organisation_id=organisation_id,
                    metadata={
                        "source": "agent",
                        "agent_name": self.name,
                        "trigger": "llm_decision",
                        "llm_stage": result.get("stage"),
                    },
                    tags=["auto", "agent_created"],
                )

        # 4. 把工单信息塞进 artifacts
        if ticket_info:
            result["ticket"] = ticket_info
            ticket_no = ticket_info.get("id", "")[:8]
            result["answer"] = (
                result.get("answer", "")
                + f"\n\n---\n我已为你创建一个保密工单 (编号 #{ticket_no}),"
                + "HR 同事会在工作时间内联系你。如紧急,请联系直线 HR 或拨打 EAP。"
            )

        # 5. 写 memory (记录用户阶段 + 是否升级)
        memory_writes: list[dict] = []
        if self.memory is not None:
            memory_writes.append({
                "scope": "working",
                "key": f"hr_stage:{user_id}",
                "value": result.get("stage", "general"),
            })
            if result.get("escalate_to_human"):
                memory_writes.append({
                    "scope": "long_term",
                    "key": f"escalated:{user_id}",
                    "value": True,
                })

        # 6. T1307: Offer 前自动发起背景调查 (HR flow / BackgroundCheck service)
        # 当阶段为 recruiting / offer 且文中提到 offer / 录用, 自动触发.
        # 失败/已有 running 检查时,不阻塞主流程.
        try:
            await _maybe_trigger_pre_offer_background_check(
                text=text,
                stage=result.get("stage", stage),
                ctx=ctx,
                hr_user_id=user_id,
                result=result,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("hr_service_agent.bg_check_hook err=%s", exc)

        # v6.0 EventBus — publish ticket.created / ticket.escalated
        try:
            ticket = result.get("ticket") or {}
            if ticket.get("id"):
                emit("ticket.created", {
                    "ticket_id": ticket["id"],
                    "employer_id": user_id,
                    "severity": ticket.get("severity", "normal"),
                    "category": ticket.get("category", "general"),
                    "summary": ticket.get("summary", "")[:200],
                }, source="agent.hr_service")
            if result.get("escalated"):
                emit("ticket.escalated", {
                    "ticket_id": ticket.get("id"),
                    "from_level": "L1",
                    "to_level": "L2",
                    "reason": result.get("escalation_reason", "unknown"),
                }, source="agent.hr_service")
        except Exception as _e:
            logger.debug("eventbus publish failed: %s", _e)

        return AgentOutput(
            agent_name=self.name,
            text=result.get("answer", "我在,有什么需要帮助?"),
            artifacts=result,
            memory_writes=memory_writes,
        )


async def _maybe_trigger_pre_offer_background_check(
    *,
    text: str,
    stage: str,
    ctx: dict,
    hr_user_id: str,
    result: dict,
) -> None:
    """T1307: HR 进入 offer 阶段时,自动 background check.

    触发条件:
      - stage ∈ {recruiting} 且 LLM 在 action_items 提到 offer/发 offer/录用
      - 或者显式 ctx["trigger_bg_check"] = True
    """
    # 显式强制触发 (v3.1 hr 工单打通后由 offers API 在发送 offer 前调用)
    if ctx.get("trigger_bg_check"):
        pass
    else:
        offer_keywords = [
            "发offer", "发 offer", "发送offer", "发出offer",
            "录用", "准备发offer", "背调",
        ]
        if stage != "recruiting":
            return
        lowered = (text or "").lower()
        if not any(kw.lower() in lowered for kw in offer_keywords):
            return

    supabase = ctx.get("supabase")
    if supabase is None:
        return

    candidate_id = (
        ctx.get("candidate_id")
        or ctx.get("offer_candidate_id")
        or hr_user_id  # 用户作为候选人时回退
    )
    if not candidate_id:
        return

    # 延迟 import 避免循环依赖
    from services.background_check_service import BackgroundCheckService

    svc = BackgroundCheckService(supabase=supabase)
    out = await svc.trigger_pre_offer(
        candidate_id=str(candidate_id),
        candidate_email=ctx.get("candidate_email"),
        candidate_name=ctx.get("candidate_name"),
        offer_id=ctx.get("offer_id"),
        job_id=ctx.get("job_id"),
    )
    if out.get("skipped"):
        result["background_check"] = {
            "status": "skipped",
            "reason": out.get("reason"),
            "existing": out.get("data"),
        }
    else:
        bc = out.get("data") or {}
        result["background_check"] = {
            "status": "initiated",
            "check_id": bc.get("check_id"),
            "provider": bc.get("provider"),
            "bg_check_url": (
                f"/background-checks/{bc.get('check_id')}"
                if bc.get("check_id") else None
            ),
        }