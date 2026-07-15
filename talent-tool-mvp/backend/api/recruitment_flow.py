"""T6109 — Recruitment flow API (contact logs + interview schedule).

Mounted under ``/api/recruitment``:

* ``POST  /api/recruitment/contact``               — record a contact log
* ``GET   /api/recruitment/contacts``              — contact history (org-scoped)
* ``POST  /api/recruitment/interview``             — schedule an interview
* ``GET   /api/recruitment/interviews``            — interview list (org-scoped)
* ``PATCH /api/recruitment/interviews/{id}/status`` — move interview status
* ``GET   /api/recruitment/kanban``                — per-candidate funnel board

Access contract (甲方合同):
    * employer (client / admin role, owns org_id) — full CRUD on their org's
      contact logs + interview schedule;
    * platform admin — everything above for every org (via ``?org_id=``).

``org_id`` is resolved from the JWT ``user_metadata.org_id`` /
``raw_app_meta_data.org_id`` claim. When the claim is missing the employer
is treated as having no org and the write endpoints 403.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from api.auth import CurrentUser, decode_supabase_jwt, require_role
from contracts.shared import UserRole
from services.matching.recruitment_flow import (
    RecruitmentFlowService,
    get_service,
)

logger = logging.getLogger("recruittech.api.recruitment_flow")
router = APIRouter()


# ---------------------------------------------------------------------------
# org_id resolution (mirrors api/recommendation_records.py)
# ---------------------------------------------------------------------------

def _resolve_org_id(request: Request, user: CurrentUser) -> Optional[str]:
    """Pull the employer's org_id from the bearer token claims.

    Falls back to a query param ``org_id`` for admin tooling.
    """
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth:
        token = auth.removeprefix("Bearer ").strip()
        if token:
            try:
                payload = decode_supabase_jwt(token)
                um = payload.get("user_metadata") or {}
                am = payload.get("app_metadata") or {}
                org = (
                    um.get("org_id")
                    or am.get("org_id")
                    or payload.get("org_id")
                )
                if org:
                    return str(org)
            except Exception:  # noqa: BLE001 — admin path still works via query
                pass
    return request.query_params.get("org_id")


def _is_admin(user: CurrentUser) -> bool:
    return user.role == UserRole.admin


def _require_org(request: Request, user: CurrentUser) -> str:
    """Resolve org_id for a write — employers must own an org."""
    org_id = _resolve_org_id(request, user)
    if _is_admin(user):
        org_id = org_id or request.query_params.get("org_id")
    if not org_id:
        raise HTTPException(
            status_code=403,
            detail="当前用户未关联组织 (org_id),无法记录招聘流程",
        )
    return org_id


# ---------------------------------------------------------------------------
# request / response schemas
# ---------------------------------------------------------------------------

class ContactMethod(str):
    pass


CONTACT_METHODS = ("phone", "email", "wechat", "sms", "video", "in_person", "other")
CONTACT_STATUSES = ("reached", "no_answer", "left_message", "rejected", "interested", "follow_up")
INTERVIEW_FORMATS = ("onsite", "video", "phone")
INTERVIEW_STATUSES = ("scheduled", "completed", "cancelled", "no_show", "rescheduled")


class CreateContactRequest(BaseModel):
    candidate_id: str = Field(..., min_length=1)
    role_id: Optional[str] = None
    contact_method: str = Field("phone")
    contact_date: Optional[str] = None
    status: str = Field("reached")
    notes: str = Field("")
    candidate_name: Optional[str] = None
    role_title: Optional[str] = None


class ContactLogOut(BaseModel):
    id: str
    candidate_id: str
    role_id: str = ""
    org_id: str = ""
    hr_id: str = ""
    contact_method: str
    contact_date: str
    status: str
    notes: str = ""
    candidate_name: str = ""
    role_title: str = ""
    created_at: str
    updated_at: str


class ScheduleInterviewRequest(BaseModel):
    candidate_id: str = Field(..., min_length=1)
    role_id: Optional[str] = None
    date: str = Field(..., min_length=1, description="YYYY-MM-DD")
    time: str = Field(..., min_length=1, description="HH:MM (24h)")
    location: str = Field("")
    format: str = Field("onsite")
    status: str = Field("scheduled")
    candidate_name: Optional[str] = None
    role_title: Optional[str] = None


class InterviewOut(BaseModel):
    id: str
    candidate_id: str
    role_id: str = ""
    org_id: str = ""
    hr_id: str = ""
    date: str
    time: str
    location: str = ""
    format: str
    status: str
    candidate_name: str = ""
    role_title: str = ""
    created_at: str
    updated_at: str


class UpdateInterviewStatusRequest(BaseModel):
    status: str = Field(..., description="新状态")


# ---------------------------------------------------------------------------
# validators
# ---------------------------------------------------------------------------

def _validate_choice(value: str, choices: tuple[str, ...], field_name: str) -> None:
    if value not in choices:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} 必须是 {list(choices)} 之一, 收到: {value}",
        )


# ---------------------------------------------------------------------------
# contact logs
# ---------------------------------------------------------------------------

@router.post("/contact", response_model=ContactLogOut, tags=["recruitment"])
async def record_contact(
    req: CreateContactRequest,
    request: Request,
    user: CurrentUser = Depends(require_role(UserRole.client, UserRole.admin)),
    service: RecruitmentFlowService = Depends(get_service),
):
    """记录一次候选人联系 (电话/邮件/微信...)."""
    _validate_choice(req.contact_method, CONTACT_METHODS, "contact_method")
    _validate_choice(req.status, CONTACT_STATUSES, "status")
    org_id = _require_org(request, user)
    payload: dict[str, Any] = {
        "candidate_id": req.candidate_id,
        "role_id": req.role_id or "",
        "org_id": org_id,
        "hr_id": str(user.id),
        "contact_method": req.contact_method,
        "contact_date": req.contact_date or None,
        "status": req.status,
        "notes": req.notes,
        "candidate_name": req.candidate_name or "",
        "role_title": req.role_title or "",
    }
    log = await service.add_contact(payload)
    return log.to_dict()


@router.get("/contacts", response_model=list[ContactLogOut], tags=["recruitment"])
async def list_contacts(
    request: Request,
    user: CurrentUser = Depends(require_role(UserRole.client, UserRole.admin)),
    service: RecruitmentFlowService = Depends(get_service),
    candidate_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """联系历史 (org-scoped)."""
    org_id = _resolve_org_id(request, user)
    if not org_id:
        return []
    if status:
        _validate_choice(status, CONTACT_STATUSES, "status")
    logs = await service.list_contacts(
        org_id=org_id,
        candidate_id=candidate_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [c.to_dict() for c in logs]


# ---------------------------------------------------------------------------
# interview schedule
# ---------------------------------------------------------------------------

@router.post("/interview", response_model=InterviewOut, tags=["recruitment"])
async def schedule_interview(
    req: ScheduleInterviewRequest,
    request: Request,
    user: CurrentUser = Depends(require_role(UserRole.client, UserRole.admin)),
    service: RecruitmentFlowService = Depends(get_service),
):
    """安排一次面试."""
    _validate_choice(req.format, INTERVIEW_FORMATS, "format")
    _validate_choice(req.status, INTERVIEW_STATUSES, "status")
    org_id = _require_org(request, user)
    payload: dict[str, Any] = {
        "candidate_id": req.candidate_id,
        "role_id": req.role_id or "",
        "org_id": org_id,
        "hr_id": str(user.id),
        "date": req.date,
        "time": req.time,
        "location": req.location,
        "format": req.format,
        "status": req.status,
        "candidate_name": req.candidate_name or "",
        "role_title": req.role_title or "",
    }
    slot = await service.schedule_interview(payload)
    return slot.to_dict()


@router.get("/interviews", response_model=list[InterviewOut], tags=["recruitment"])
async def list_interviews(
    request: Request,
    user: CurrentUser = Depends(require_role(UserRole.client, UserRole.admin)),
    service: RecruitmentFlowService = Depends(get_service),
    candidate_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """面试列表 (org-scoped)."""
    org_id = _resolve_org_id(request, user)
    if not org_id:
        return []
    if status:
        _validate_choice(status, INTERVIEW_STATUSES, "status")
    slots = await service.list_interviews(
        org_id=org_id,
        candidate_id=candidate_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [s.to_dict() for s in slots]


@router.patch(
    "/interviews/{interview_id}/status",
    response_model=InterviewOut,
    tags=["recruitment"],
)
async def update_interview_status(
    interview_id: str,
    req: UpdateInterviewStatusRequest,
    request: Request,
    user: CurrentUser = Depends(require_role(UserRole.client, UserRole.admin)),
    service: RecruitmentFlowService = Depends(get_service),
):
    """更新面试状态 (scheduled → completed/cancelled/no_show/rescheduled)."""
    _validate_choice(req.status, INTERVIEW_STATUSES, "status")
    org_id = _resolve_org_id(request, user)
    slot = await service.get_interview(interview_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="面试不存在")
    # employers can only touch interviews in their own org (admin bypasses)
    if org_id and slot.org_id and slot.org_id != org_id and not _is_admin(user):
        raise HTTPException(status_code=403, detail="无权修改其他组织的面试")
    updated = await service.update_interview_status(interview_id, req.status)
    if updated is None:
        raise HTTPException(status_code=404, detail="面试不存在")
    return updated.to_dict()


# ---------------------------------------------------------------------------
# kanban board
# ---------------------------------------------------------------------------

@router.get("/kanban", tags=["recruitment"])
async def kanban(
    request: Request,
    user: CurrentUser = Depends(require_role(UserRole.client, UserRole.admin)),
    service: RecruitmentFlowService = Depends(get_service),
):
    """招聘流程看板: 联系 → 面试 → 结果 (按候选人聚合)."""
    org_id = _resolve_org_id(request, user)
    if not org_id:
        return {"org_id": "", "candidates": [], "totals": {"contacted": 0, "interviewing": 0, "completed": 0}}
    return await service.kanban(org_id=org_id)
