"""Probation API (T2404).

Endpoints:
    GET  /api/probation/me
    GET  /api/probation/team/{org_id}
    GET  /api/probation/employees/{employee_id}
    POST /api/probation/employees/{employee_id}/onboard
    POST /api/probation/{review_id}/review
    POST /api/probation/{review_id}/complete
    POST /api/probation/{review_id}/extend
    GET  /api/probation/tasks/due
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from services.employer.probation_service import (
    DIMENSIONS,
    ProbationService,
    get_probation_service,
)

logger = logging.getLogger("recruittech.api.probation")
router = APIRouter()


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class OnboardRequest(BaseModel):
    employee_id: str
    org_id: str
    hire_date: Optional[str] = None  # ISO 8601; defaults now


class ReviewSubmission(BaseModel):
    review_stage: str = Field(..., description="30 | 90 | 180 | final")
    scores: dict[str, int] = Field(..., description="5 维度 1-5 分")
    comments: Optional[str] = None


class CompleteRequest(BaseModel):
    notes: Optional[str] = None


class ExtendRequest(BaseModel):
    extension_days: int = Field(..., ge=1, le=90)
    reason: Optional[str] = None


class DirectReviewSubmission(BaseModel):
    employee_id: str
    org_id: str
    manager_id: Optional[str] = None
    review_stage: str
    scores: dict[str, int]
    comments: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/me")
async def my_probation(
    user: CurrentUser = Depends(get_current_user),
):
    """员工视角: 自己的试用期 + 任务."""
    svc = get_probation_service()
    # Demo mock: 真实场景从 DB 查询
    reviews = [
        {
            "id": f"demo-review-{user.id[:6]}",
            "review_stage": "30",
            "review_date": "2026-06-10",
            "scores": {"performance": 4, "learning": 5, "integration": 4, "attitude": 5, "potential": 4},
            "comments": "适应良好, 学习速度快.",
            "status": "passed",
        }
    ]
    tasks = [
        {
            "id": "demo-task-90",
            "type": "review_90",
            "title": "D+90 评估",
            "description": "90 天试用期评估 (5 维度)",
            "due_at": "2026-08-09T00:00:00+00:00",
        },
        {
            "id": "demo-task-180",
            "type": "review_180",
            "title": "D+180 转正评估",
            "description": "180 天转正评估",
            "due_at": "2026-11-09T00:00:00+00:00",
        },
    ]
    return svc.summarize_employee(user.id, reviews, tasks)


@router.get("/team/{org_id}")
async def team_probation(
    org_id: str,
    user: CurrentUser = Depends(get_current_user),
    _employees: Optional[str] = Query(None, description="JSON 数组, 来自调用方过滤"),
):
    """HR/经理视角: 团队试用期列表."""
    if user.role.value not in ("hr", "manager", "admin"):
        raise HTTPException(status_code=403, detail="hr/manager role required")
    svc = get_probation_service()
    # Demo data (真实场景从 DB 查询)
    employees = [
        {
            "id": f"emp-{org_id[:4]}-001",
            "name": "张三",
            "hire_date": "2026-04-01",
            "tags": ["on_track"],
            "latest_score": 4.2,
        },
        {
            "id": f"emp-{org_id[:4]}-002",
            "name": "李四",
            "hire_date": "2026-05-15",
            "tags": ["pending_review"],
            "latest_score": 3.6,
        },
        {
            "id": f"emp-{org_id[:4]}-003",
            "name": "王五",
            "hire_date": "2026-01-10",
            "tags": ["confirmed"],
            "latest_score": 4.8,
        },
    ]
    return svc.summarize_team(org_id, employees)


@router.get("/employees/{employee_id}")
async def get_employee_probation(
    employee_id: str,
    _user: CurrentUser = Depends(get_current_user),
):
    """单个员工的完整试用期视图."""
    svc = get_probation_service()
    return svc.summarize_employee(employee_id, reviews=[], tasks=[])


@router.post("/employees/{employee_id}/onboard")
async def onboard_employee(
    employee_id: str,
    body: OnboardRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """新员工入职: 自动生成 5 个任务."""
    if user.role.value not in ("hr", "admin", "manager"):
        raise HTTPException(status_code=403, detail="hr/manager role required")
    svc = get_probation_service()
    if body.hire_date:
        try:
            hire = datetime.fromisoformat(body.hire_date.replace("Z", "+00:00"))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        hire = datetime.now(timezone.utc)
    tasks = svc.create_onboarding_tasks(employee_id, body.org_id, hire)
    return {"employee_id": employee_id, "tasks_created": len(tasks), "tasks": tasks}


@router.post("/{review_id}/review")
async def submit_review(
    review_id: str,
    body: ReviewSubmission,
    user: CurrentUser = Depends(get_current_user),
):
    """提交评估 — 经理视角."""
    if user.role.value not in ("hr", "manager", "admin"):
        raise HTTPException(status_code=403, detail="manager role required")
    svc = get_probation_service()
    try:
        review = svc.submit_review(
            employee_id="",  # 由 review_id 查询
            manager_id=user.id,
            org_id="",
            review_stage=body.review_stage,
            scores=body.scores,
            comments=body.comments,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    review["id"] = review_id
    return review


@router.post("/reviews/submit")
async def submit_review_direct(
    body: DirectReviewSubmission,
    user: CurrentUser = Depends(get_current_user),
):
    """直接提交评估 (含 employee_id/org_id)."""
    if user.role.value not in ("hr", "manager", "admin"):
        raise HTTPException(status_code=403, detail="manager role required")
    svc = get_probation_service()
    try:
        review = svc.submit_review(
            employee_id=body.employee_id,
            manager_id=body.manager_id or user.id,
            org_id=body.org_id,
            review_stage=body.review_stage,
            scores=body.scores,
            comments=body.comments,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return review


@router.post("/{review_id}/complete")
async def complete_review(
    review_id: str,
    body: CompleteRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """转正."""
    if user.role.value not in ("hr", "manager", "admin"):
        raise HTTPException(status_code=403, detail="manager role required")
    svc = get_probation_service()
    result = svc.complete_probation(review_id, body.notes)
    return result


@router.post("/{review_id}/extend")
async def extend_review(
    review_id: str,
    body: ExtendRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """延长试用期 1-90 天."""
    if user.role.value not in ("hr", "manager", "admin"):
        raise HTTPException(status_code=403, detail="manager role required")
    svc = get_probation_service()
    try:
        result = svc.extend_probation(
            review_id,
            body.extension_days,
            body.reason,
            approved_by=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.get("/tasks/due")
async def due_tasks(
    lead_days: int = Query(3, ge=0, le=30),
    user: CurrentUser = Depends(get_current_user),
):
    """HR: 找出今天及接下来 N 天内到期的任务 (需发送提醒)."""
    if user.role.value not in ("hr", "manager", "admin"):
        raise HTTPException(status_code=403, detail="hr/manager role required")
    svc = get_probation_service()
    from services.employer.probation_scheduler import daily_check_tasks
    result = daily_check_tasks([])
    return result
