"""v8.1 API — 6 P1 任务的对外接口.

路由前缀: /api/v8_1/*
集成 service_toggle: 所有路由都跑 check_service_access.

T3601 — relationship + outreach
T3602 — journal_evaluator + action_items
T3603 — proactive_scheduler
T3604 — emotion_care
T3605 — profile_confirm
T3606 — plan_tracker v3
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import CurrentUser, get_current_user
from services.platform.service_toggle import service_toggle

router = APIRouter(prefix="/api/v8_1", tags=["v8.1"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _require_service(name: str) -> None:
    """Service toggle check."""
    if not service_toggle.is_enabled(name, org_id="", plan="free", role=""):
        raise HTTPException(status_code=404, detail=f"service {name} disabled")


# ---------------------------------------------------------------------------
# T3601 — Relationship
# ---------------------------------------------------------------------------
@router.get("/relationship/state")
async def get_relationship_state(user_id: str = Query(...)):
    _require_service("agent.profile")
    from services.jobseeker.relationship import get_relationship_service

    rel = get_relationship_service()
    return {
        "state": rel.get_state(user_id).to_dict(),
        "tone": rel.get_tone(user_id),
    }


@router.get("/relationship/events")
async def list_relationship_events(user_id: str, limit: int = 50):
    _require_service("agent.profile")
    from services.jobseeker.relationship import get_relationship_service

    rel = get_relationship_service()
    events = rel.list_events(user_id, limit=limit)
    return {"events": [e.to_dict() for e in events]}


@router.post("/relationship/update")
async def update_relationship_stage(body: dict):
    _require_service("agent.profile")
    from services.jobseeker.relationship import get_relationship_service

    rel = get_relationship_service()
    from_stage, to_stage = rel.update_stage(
        body["user_id"],
        body["event_type"],
        context=body.get("context") or {},
    )
    return {"from_stage": from_stage, "to_stage": to_stage}


@router.post("/relationship/touch")
async def touch_relationship_interaction(body: dict):
    _require_service("agent.profile")
    from services.jobseeker.relationship import get_relationship_service

    rel = get_relationship_service()
    rel.touch_interaction(body["user_id"])
    return {"ok": True}


# ---------------------------------------------------------------------------
# T3601 — Outreach
# ---------------------------------------------------------------------------
class OutreachReq(BaseModel):
    user_id: str
    reason: str
    name: str = "同学"
    days: int = 0
    force: bool = False


@router.post("/outreach/reach_out")
async def outreach_reach_out(req: OutreachReq):
    _require_service("agent.profile")
    from services.jobseeker.proactive_outreach import get_outreach_service

    svc = get_outreach_service()
    msg = await svc.reach_out(
        user_id=req.user_id,
        reason=req.reason,
        name=req.name,
        days=req.days,
        force=req.force,
    )
    return msg.to_dict()


@router.post("/outreach/run_scheduled")
async def outreach_run_scheduled(max_users: int = 100):
    _require_service("agent.profile")
    from services.jobseeker.proactive_outreach import get_outreach_service

    svc = get_outreach_service()
    msgs = await svc.run_scheduled_pass(max_users=max_users)
    return {"count": len(msgs), "messages": [m.to_dict() for m in msgs]}


# ---------------------------------------------------------------------------
# T3602 — Journal Evaluator
# ---------------------------------------------------------------------------
class EvaluateReq(BaseModel):
    text: str
    role: str = "backend"
    user_id: str = ""


@router.post("/journal/evaluate")
async def journal_evaluate(req: EvaluateReq):
    _require_service("agent.daily_journal")
    from services.jobseeker.journal_evaluator import get_journal_evaluator

    ev = get_journal_evaluator().evaluate(
        text=req.text,
        role=req.role,
        context={"user_id": req.user_id},
    )
    return ev.to_dict()


@router.get("/journal/trend")
async def journal_rating_trend(user_id: str, days: int = 30):
    _require_service("agent.daily_journal")
    from services.jobseeker.journal_evaluator import get_journal_evaluator

    return {"trend": get_journal_evaluator().rating_trend(user_id, days=days)}


# ---------------------------------------------------------------------------
# T3602 — Action Items
# ---------------------------------------------------------------------------
class ActionItemUpdateReq(BaseModel):
    item_id: str
    status: Optional[str] = None
    quality_score: Optional[float] = None
    due_date: Optional[str] = None


@router.get("/action_items")
async def list_action_items(user_id: str, status: Optional[str] = None, role: Optional[str] = None):
    _require_service("agent.daily_journal")
    from services.jobseeker.journal_evaluator import get_journal_evaluator

    items = get_journal_evaluator().list_action_items(user_id, status=status, role=role)
    return {"items": [i.to_dict() for i in items]}


@router.post("/action_items/update")
async def update_action_item(req: ActionItemUpdateReq):
    _require_service("agent.daily_journal")
    from services.jobseeker.journal_evaluator import get_journal_evaluator

    try:
        item = get_journal_evaluator().update_action_item(
            req.item_id,
            status=req.status,
            quality_score=req.quality_score,
            due_date=req.due_date,
        )
        return {"item": item.to_dict()}
    except KeyError:
        raise HTTPException(404, "action item not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/action_items/due")
async def action_items_due(hours: int = 24):
    _require_service("agent.daily_journal")
    from services.jobseeker.journal_evaluator import get_journal_evaluator

    items = get_journal_evaluator().due_items(hours=hours)
    return {"items": [i.to_dict() for i in items]}


# ---------------------------------------------------------------------------
# T3603 — Proactive Scheduler
# ---------------------------------------------------------------------------
class RegisterUserReq(BaseModel):
    user_id: str
    stage: str = "active_job_seeker"
    new_jobs_count: int = 0
    upcoming_interview_at: Optional[str] = None


@router.post("/proactive/register")
async def proactive_register(req: RegisterUserReq):
    _require_service("agent.profile")
    from services.platform.proactive_scheduler import get_proactive_scheduler

    sched = get_proactive_scheduler()
    sched.register_user(
        req.user_id,
        stage=req.stage,
        new_jobs_count=req.new_jobs_count,
        upcoming_interview_at=req.upcoming_interview_at,
    )
    return {"ok": True}


@router.post("/proactive/run")
async def proactive_run(max_users: int = 100):
    _require_service("agent.profile")
    from services.platform.proactive_scheduler import get_proactive_scheduler

    sched = get_proactive_scheduler()
    logs = await sched.run_once(max_users=max_users)
    return {
        "count": len(logs),
        "logs": [l.to_dict() for l in logs],
        "stats": sched.stats(),
    }


@router.get("/proactive/stats")
async def proactive_stats():
    _require_service("agent.profile")
    from services.platform.proactive_scheduler import get_proactive_scheduler

    return get_proactive_scheduler().stats()


@router.get("/proactive/logs")
async def proactive_logs(user_id: Optional[str] = None, limit: int = 100):
    _require_service("agent.profile")
    from services.platform.proactive_scheduler import get_proactive_scheduler

    logs = get_proactive_scheduler().get_logs(user_id=user_id, limit=limit)
    return {"logs": [l.to_dict() for l in logs]}


# ---------------------------------------------------------------------------
# T3604 — Emotion Care
# ---------------------------------------------------------------------------
class CareTriggerReq(BaseModel):
    user_id: str
    risk_level: str
    primary_emotion: str
    trigger_text: str
    intensity: float = 0.5


@router.post("/emotion/care/trigger")
async def emotion_care_trigger(req: CareTriggerReq):
    _require_service("agent.emotion")
    from services.jobseeker.emotion_care import get_emotion_care_service

    ticket = get_emotion_care_service().trigger_care(
        req.user_id,
        risk_level=req.risk_level,
        primary_emotion=req.primary_emotion,
        trigger_text=req.trigger_text,
        intensity=req.intensity,
    )
    return ticket.to_dict()


@router.get("/emotion/care/tickets")
async def emotion_care_tickets(user_id: Optional[str] = None, level: Optional[str] = None):
    _require_service("agent.emotion")
    from services.jobseeker.emotion_care import get_emotion_care_service

    tickets = get_emotion_care_service().list_tickets(user_id=user_id, level=level)
    return {"tickets": [t.to_dict() for t in tickets]}


@router.get("/emotion/care/tickets/{ticket_id}/actions")
async def emotion_care_actions(ticket_id: str):
    _require_service("agent.emotion")
    from services.jobseeker.emotion_care import get_emotion_care_service

    return {"actions": [a.to_dict() for a in get_emotion_care_service().list_actions(ticket_id)]}


@router.post("/emotion/care/tickets/{ticket_id}/close")
async def emotion_care_close(ticket_id: str):
    _require_service("agent.emotion")
    from services.jobseeker.emotion_care import get_emotion_care_service

    ticket = get_emotion_care_service().close_ticket(ticket_id)
    if not ticket:
        raise HTTPException(404, "ticket not found")
    return ticket.to_dict()


@router.get("/emotion/care/dashboard")
async def emotion_care_dashboard():
    """HR Mothership wellness dashboard."""
    _require_service("agent.emotion")
    from services.jobseeker.emotion_care import get_emotion_care_service

    return get_emotion_care_service().dashboard_summary()


@router.get("/emotion/care/resources")
async def emotion_care_resources(category: str = "general_wellbeing", limit: int = 5):
    _require_service("agent.emotion")
    from services.jobseeker.emotion_care import get_emotion_care_service

    return {
        "category": category,
        "resources": get_emotion_care_service().resources_for(category, limit=limit),
    }


# ---------------------------------------------------------------------------
# T3605 — Profile Confirm
# ---------------------------------------------------------------------------
class CorrectionReq(BaseModel):
    user_id: str
    field_path: str
    original_value: str
    corrected_value: str
    reason: str = ""


@router.post("/profile/correction")
async def profile_correction(req: CorrectionReq):
    _require_service("agent.clarifier")
    from agents.jobseeker.clarifier_agent import record_user_correction

    return record_user_correction(
        req.user_id,
        field_path=req.field_path,
        original_value=req.original_value,
        corrected_value=req.corrected_value,
        reason=req.reason,
    )


class UpvoteReq(BaseModel):
    user_id: str
    field_path: str


@router.post("/profile/upvote")
async def profile_upvote(req: UpvoteReq):
    _require_service("agent.clarifier")
    from agents.jobseeker.clarifier_agent import upvote_profile_field

    return upvote_profile_field(req.user_id, field_path=req.field_path)


@router.get("/profile/understanding")
async def profile_understanding(user_id: str):
    """AI 理解的我 — 从 long-term memory 取最新画像 + 信心分."""
    _require_service("agent.clarifier")
    try:
        from services.memory.mem0_store import recall_memory

        profile = recall_memory(user_id, key="profile", default={})
    except Exception:
        profile = {}
    try:
        from services.memory.mem0_store import recall_memory as _r2

        clarification = _r2(user_id, key="clarification", default={})
    except Exception:
        clarification = {}
    return {
        "user_id": user_id,
        "profile": profile,
        "clarification": clarification,
    }


# ---------------------------------------------------------------------------
# T3606 — Plan Tracker v3
# ---------------------------------------------------------------------------
class CheckinReq(BaseModel):
    user_id: str
    item_title: str
    note: str = ""


@router.post("/plan/checkin")
async def plan_checkin(req: CheckinReq):
    _require_service("agent.career_planner")
    from services.jobseeker.plan_tracker import daily_checkin

    return daily_checkin(req.user_id, item_title=req.item_title, note=req.note)


@router.get("/plan/suggestions")
async def plan_suggestions(user_id: str):
    _require_service("agent.career_planner")
    from services.jobseeker.plan_tracker import adjust_suggestions

    return {"suggestions": adjust_suggestions(user_id)}


@router.get("/plan/gantt")
async def plan_gantt(user_id: str):
    _require_service("agent.career_planner")
    from services.jobseeker.plan_tracker import gantt_data

    return gantt_data(user_id)


class LinkActionReq(BaseModel):
    user_id: str
    action_item_id: str
    plan_item_title: str


@router.post("/plan/link_action")
async def plan_link_action(req: LinkActionReq):
    _require_service("agent.career_planner")
    from services.jobseeker.plan_tracker import link_action_item_to_plan

    return link_action_item_to_plan(req.user_id, req.action_item_id, req.plan_item_title)