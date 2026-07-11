"""Escalation API (T704) — 一键升级人工 + 自动建议 HRBP.

Endpoints:
    POST /api/escalation   { text, department?, priority?, suggested_hrbp? }
        → 创建工单 + 推断部门 + 自动建议 HRBP assignee
    GET  /api/escalation/suggest-hrbp?department=...
        → 返回建议的 HRBP 列表
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin
from services.persona_memory import infer_prefs_from_text

logger = logging.getLogger("recruittech.api.escalation")
router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class EscalationRequest(BaseModel):
    text: str
    department: Optional[str] = None
    priority: Optional[str] = None     # low | normal | high | urgent
    suggested_hrbp: bool = True
    organisation_id: Optional[str] = None
    context: dict = {}


class EscalationResponse(BaseModel):
    success: bool
    ticket_id: Optional[str] = None
    ticket_no: Optional[str] = None
    priority: str = "normal"
    category: str = "complaint"
    department: str = "general"
    suggested_hrbp: Optional[dict] = None
    assignee_id: Optional[str] = None
    message: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
SENSITIVE_URGENT = ["不想活了", "想轻生", "自残", "工伤", "性骚扰", "霸凌", "歧视", "拖欠工资", "解雇", "开除"]
SENSITIVE_HIGH = ["降薪", "加班费", "辞退", "违纪处分", "仲裁", "诉讼", "欺凌"]


def _infer_priority(text: str, default: Optional[str] = None) -> str:
    if default and default in ("low", "normal", "high", "urgent"):
        return default
    if any(kw in text for kw in SENSITIVE_URGENT):
        return "urgent"
    if any(kw in text for kw in SENSITIVE_HIGH):
        return "high"
    return "normal"


def _infer_department(text: str, ctx_dept: Optional[str] = None) -> str:
    if ctx_dept:
        return ctx_dept
    text_lower = text.lower()
    if any(kw in text for kw in ["工资", "加班费", "薪资", "五险一金", "个税"]):
        return "payroll"
    if any(kw in text for kw in ["技术", "代码", "系统", "权限", "it"]):
        return "it"
    if any(kw in text for kw in ["招聘", "面试", "offer"]):
        return "recruiting"
    if any(kw in text for kw in ["培训", "学习", "课程", "认证"]):
        return "training"
    if any(kw in text for kw in ["绩效", "考核", "kpi"]):
        return "performance"
    return "general"


async def _suggest_hrbp(supabase, department: str, organisation_id: Optional[str]) -> Optional[dict]:
    """在 org_members 里找 role='hr' 或 'admin' 的成员,优先匹配部门。

    返回 {user_id, name, role, match_score} 或 None。
    """
    try:
        q = supabase.table("org_members").select("user_id, role, department, display_name")
        if organisation_id is not None:
            q = q.eq("organisation_id", organisation_id)
        r = q.execute()
        rows = r.data or []
        if not rows:
            return None
        # 简单打分: hr 角色 +1, dept 匹配 +1
        best = None
        best_score = -1
        for row in rows:
            score = 0
            if row.get("role") in ("hr", "admin"):
                score += 2
            if row.get("department") == department:
                score += 1
            if row.get("role") == "dept_head" and row.get("department") == department:
                score += 1
            if score > best_score:
                best_score = score
                best = row
        if best:
            return {
                "user_id": best.get("user_id"),
                "name": best.get("display_name") or best.get("user_id"),
                "role": best.get("role"),
                "department": best.get("department"),
                "match_score": best_score,
            }
        # 没有 hr 也要有兜底
        return {
            "user_id": rows[0].get("user_id"),
            "name": rows[0].get("display_name") or rows[0].get("user_id"),
            "role": rows[0].get("role"),
            "department": rows[0].get("department"),
            "match_score": 0,
        }
    except Exception as e:  # noqa: BLE001
        logger.warning(f"suggest_hrbp failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
@router.post("", response_model=EscalationResponse)
async def escalate_to_human(
    body: EscalationRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """一键升级人工 — 创建工单 + 自动建议 HRBP。"""
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=400, detail="text is empty")

    supabase = get_supabase_admin()
    priority = _infer_priority(body.text, body.priority)
    department = _infer_department(body.text, body.department)

    # 1) 建议 HRBP
    suggested = None
    assignee_id = None
    if body.suggested_hrbp:
        suggested = await _suggest_hrbp(supabase, department, body.organisation_id)
        if suggested:
            assignee_id = suggested.get("user_id")

    # 2) 创建工单
    ticket_id: Optional[str] = None
    ticket_no: Optional[str] = None
    try:
        from services.ticket_service import create_ticket

        ticket = create_ticket(
            supabase,
            user_id=str(user.id),
            auto_create=True,
            title=f"[升级人工] {body.text[:50]}",
            description=body.text,
            priority=priority,
            category="complaint",
            organisation_id=body.organisation_id,
            assignee_id=assignee_id,
            metadata={
                "source": "user_escalation",
                "trigger": "manual",
                "department": department,
                "context": body.context,
                "asker_role": user.role.value,
                "suggested_hrbp": suggested,
            },
            tags=["escalated", "manual", f"dept:{department}"],
        )
        ticket_id = ticket.id if hasattr(ticket, "id") else ticket.get("id", "")
        ticket_no = getattr(ticket, "no", None) or ticket.get("no")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"escalation create_ticket failed: {e}")
        raise HTTPException(status_code=500, detail=f"failed to create ticket: {e}")

    return EscalationResponse(
        success=True,
        ticket_id=ticket_id,
        ticket_no=ticket_no,
        priority=priority,
        category="complaint",
        department=department,
        suggested_hrbp=suggested,
        assignee_id=assignee_id,
        message=(
            f"已创建工单 #{str(ticket_no or ticket_id)[:8]}"
            + (f",已分配给 {suggested.get('name')}" if suggested else ",稍后分配 HR")
        ),
    )


@router.get("/suggest-hrbp")
async def suggest_hrbp_endpoint(
    department: str = Query("general"),
    organisation_id: Optional[str] = Query(None),
    user: CurrentUser = Depends(get_current_user),
):
    """返回建议的 HRBP 列表 (前端预填时用)。"""
    supabase = get_supabase_admin()
    suggested = await _suggest_hrbp(supabase, department, organisation_id)
    return {"suggested_hrbp": suggested, "department": department}