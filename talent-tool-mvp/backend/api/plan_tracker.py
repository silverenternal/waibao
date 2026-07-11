"""职业计划追踪 API (T607).

路径:
    POST /api/plan/adjust              { user_id, action, target_item, detail, delta_days }
    GET  /api/plan/progress/{user_id}
    POST /api/plan/checkin             { user_id, item_title, progress_delta, note }
    POST /api/plan/init                { user_id, plan_data }  (把 CareerPlanner 输出落地)
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from api.auth import CurrentUser, get_current_user
from services.plan_tracker import get_plan_tracker

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class AdjustRequest(BaseModel):
    user_id: str
    action: str = Field(..., pattern="^(delay|accelerate|replace|add|remove)$")
    target_item: str
    detail: str = ""
    delta_days: int = 0


class CheckinRequest(BaseModel):
    user_id: str
    item_title: str
    progress_delta: float = Field(0.1, ge=0.0, le=1.0)
    note: str = ""


class InitPlanRequest(BaseModel):
    user_id: str
    plan_data: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/adjust")
async def adjust_plan(
    req: AdjustRequest, _: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    svc = get_plan_tracker()
    try:
        adj = svc.adjust(
            req.user_id,
            req.action,
            req.target_item,
            detail=req.detail,
            delta_days=req.delta_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "adjustment": adj.to_dict()}


@router.post("/checkin")
async def checkin(
    req: CheckinRequest, _: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    svc = get_plan_tracker()
    try:
        ck = svc.checkin(
            req.user_id,
            req.item_title,
            progress_delta=req.progress_delta,
            note=req.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "checkin": ck.to_dict()}


@router.get("/progress/{user_id}")
async def progress(
    user_id: str = Path(..., min_length=1),
    _: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    svc = get_plan_tracker()
    return svc.progress(user_id)


@router.post("/init")
async def init_plan(
    req: InitPlanRequest, _: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    """把 CareerPlannerAgent 的输出导入 tracker."""
    svc = get_plan_tracker()
    plan = svc.create_plan(req.user_id, plan_data=req.plan_data)
    return {"status": "ok", "plan": plan.to_dict()}


@router.get("/history/{user_id}")
async def history(
    user_id: str = Path(..., min_length=1),
    _: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """返回最近打卡 + 调整历史."""
    svc = get_plan_tracker()
    return {
        "user_id": user_id,
        "checkins": [c.to_dict() for c in svc.list_checkins(user_id)],
        "adjustments": [a.to_dict() for a in svc.list_adjustments(user_id)],
    }


__all__ = ["router"]