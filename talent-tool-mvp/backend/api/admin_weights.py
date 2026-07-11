"""T903 — Admin: 权重查看 / 人工覆盖 / 应用建议.

GET   /api/admin/weights                — 当前权重 + 历史
PATCH /api/admin/weights                — 人工覆盖
POST  /api/admin/weights/apply          — 立即应用待审批建议
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import CurrentUser, require_role
from api.deps import get_supabase_admin
from contracts.shared import UserRole
from services.feedback_loop import (
    DEFAULT_WEIGHTS,
    aggregate_outcomes,
    apply_adjustment,
    compute_weight_adjustment,
    get_current_weights,
)

logger = logging.getLogger("recruittech.api.admin_weights")
router = APIRouter()


class WeightsUpdate(BaseModel):
    weights: dict[str, float] = Field(...)
    reason: str = Field(default="manual override", max_length=500)


class ApplyRequest(BaseModel):
    weights: dict[str, float]
    reason: str = Field(default="manual apply", max_length=500)


@router.get("")
async def list_weights(user: CurrentUser = Depends(require_role(UserRole.admin))):
    """当前权重 + 最近 N 条历史."""
    supabase = get_supabase_admin()
    current = await get_current_weights(supabase)

    history: list[dict[str, Any]] = []
    try:
        resp = (
            supabase.table("settings_audit")
            .select("*")
            .eq("action", "weight_adjustment")
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        for row in resp.data or []:
            history.append(
                {
                    "id": row.get("id"),
                    "actor": row.get("actor"),
                    "weights": row.get("weights"),
                    "reason": row.get("reason"),
                    "created_at": row.get("created_at"),
                }
            )
    except Exception as exc:
        logger.debug(f"history fetch failed: {exc}")

    pending: list[dict[str, Any]] = []
    try:
        resp = (
            supabase.table("settings")
            .select("*")
            .eq("key", "matching_weights")
            .eq("status", "pending")
            .execute()
        )
        for row in resp.data or []:
            v = row.get("value")
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except Exception:
                    v = {}
            pending.append(
                {
                    "id": row.get("id"),
                    "weights": v,
                    "reason": row.get("reason"),
                    "actor": row.get("actor"),
                    "updated_at": row.get("updated_at"),
                }
            )
    except Exception as exc:
        logger.debug(f"pending fetch failed: {exc}")

    return {
        "current": current,
        "defaults": DEFAULT_WEIGHTS,
        "history": history,
        "pending": pending,
    }


@router.patch("")
async def override_weights(
    body: WeightsUpdate,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """管理员直接覆盖权重."""
    supabase = get_supabase_admin()
    weights = body.weights
    if not isinstance(weights, dict) or not weights:
        raise HTTPException(status_code=400, detail="weights must be a non-empty dict")

    result = await apply_adjustment(
        weights,
        actor=str(user.id),
        reason=body.reason,
        supabase=supabase,
        require_approval=False,
    )
    return {"applied": True, **result}


@router.post("/apply")
async def apply_pending(
    body: ApplyRequest,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """立即应用建议(把 pending 提升为 active)."""
    supabase = get_supabase_admin()
    result = await apply_adjustment(
        body.weights,
        actor=str(user.id),
        reason=body.reason,
        supabase=supabase,
        require_approval=False,
    )
    return {"applied": True, **result}


@router.post("/recommend")
async def generate_recommendation(
    since_days: int = 7,
    user: CurrentUser = Depends(require_role(UserRole.admin)),
):
    """立即触发一次建议生成(用于手动探索)."""
    supabase = get_supabase_admin()
    metrics = await aggregate_outcomes(since_days=since_days, supabase=supabase)
    current = await get_current_weights(supabase)
    adj = await compute_weight_adjustment(current, metrics)
    return {
        "metrics": metrics.to_dict(),
        "current": current,
        "recommendation": adj.to_dict(),
        "generated_at": datetime.utcnow().isoformat(),
    }