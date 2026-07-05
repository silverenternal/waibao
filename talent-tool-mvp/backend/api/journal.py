"""日报 API (T102)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from agents.registry import registry
from agents.runtime import AgentInput
from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin

logger = logging.getLogger("recruittech.api.journal")
router = APIRouter()


class JournalSubmit(BaseModel):
    content: str
    mood_score: Optional[float] = None


@router.post("")
async def submit_journal(
    body: JournalSubmit,
    user: CurrentUser = Depends(get_current_user),
):
    """提交日记,触发 Daily Journal Agent."""
    agent = registry.get_or_raise("daily_journal_agent")
    out = await agent.run(AgentInput(
        user_id=str(user.id),
        persona=user.role.value,
        text=body.content,
        context={"mood_score": body.mood_score} if body.mood_score is not None else {},
    ))
    return {
        "text": out.text,
        "artifacts": out.artifacts,
        "success": out.success,
    }


@router.get("/timeline")
async def get_journal_timeline(
    days: int = Query(default=30, le=365),
    user: CurrentUser = Depends(get_current_user),
):
    """获取我的日记时间线."""
    supabase = get_supabase_admin()
    result = (
        supabase.table("daily_journals")
        .select("id, journal_date, content, mood_score, ai_rating, ai_advice, ai_warnings, ai_action_items")
        .eq("user_id", str(user.id))
        .order("journal_date", desc=True)
        .limit(days)
        .execute()
    )
    return {"data": result.data or [], "total": len(result.data or [])}


@router.get("/today")
async def get_today_journal(user: CurrentUser = Depends(get_current_user)):
    """获取今天的日记(若已提交)."""
    supabase = get_supabase_admin()
    today = datetime.utcnow().date().isoformat()
    result = (
        supabase.table("daily_journals")
        .select("*")
        .eq("user_id", str(user.id))
        .eq("journal_date", today)
        .maybe_single()
        .execute()
    )
    return result.data or {}