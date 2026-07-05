"""情绪 API (T103)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from agents.registry import registry
from agents.runtime import AgentInput
from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin

logger = logging.getLogger("recruittech.api.emotion")
router = APIRouter()


@router.post("/detect")
async def detect_emotion(
    text: str,
    user: CurrentUser = Depends(get_current_user),
):
    """对一段文本做情感分析 + 共情回应."""
    agent = registry.get_or_raise("emotion_agent")
    out = await agent.run(AgentInput(
        user_id=str(user.id),
        persona=user.role.value,
        text=text,
    ))
    return {
        "response": out.text,
        "emotion": out.artifacts.get("emotion"),
        "intensity": out.artifacts.get("intensity"),
        "sentiment": out.artifacts.get("sentiment"),
        "needs_attention": out.artifacts.get("needs_attention"),
    }


@router.get("/timeline")
async def get_emotion_timeline(
    days: int = Query(default=30, le=365),
    user: CurrentUser = Depends(get_current_user),
):
    """情绪时间线(可视化用)."""
    supabase = get_supabase_admin()
    result = (
        supabase.table("emotion_timeline")
        .select("recorded_at, primary_emotion, intensity, sentiment, needs_attention, trigger_text")
        .eq("user_id", str(user.id))
        .order("recorded_at", desc=True)
        .limit(days)
        .execute()
    )
    return {"data": result.data or []}


@router.get("/alerts")
async def get_emotion_alerts(user: CurrentUser = Depends(get_current_user)):
    """HR/管理员视角: 情绪告警列表."""
    if user.role.value not in ("hr", "admin", "talent_partner"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Forbidden")

    supabase = get_supabase_admin()
    result = (
        supabase.table("emotion_timeline")
        .select("user_id, primary_emotion, sentiment, recorded_at, trigger_text, needs_attention")
        .eq("needs_attention", True)
        .order("recorded_at", desc=True)
        .limit(100)
        .execute()
    )
    return {"alerts": result.data or []}