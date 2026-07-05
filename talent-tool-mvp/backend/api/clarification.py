"""Clarification API (T104 + T208)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agents.registry import registry
from agents.runtime import AgentInput
from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin

logger = logging.getLogger("recruittech.api.clarification")
router = APIRouter()


@router.post("/synthesize")
async def synthesize_candidate(user: CurrentUser = Depends(get_current_user)):
    """综合求职者画像+真实需求."""
    supabase = get_supabase_admin()

    # 拉取所有上下文
    journals = supabase.table("daily_journals").select("content, ai_rating, mood_score").eq(
        "user_id", str(user.id)
    ).order("journal_date", desc=True).limit(30).execute().data or []
    convs = supabase.table("conversations").select("role, content, emotion").eq(
        "user_id", str(user.id)
    ).order("created_at", desc=True).limit(50).execute().data or []
    emotions = supabase.table("emotion_timeline").select("primary_emotion, sentiment, recorded_at").eq(
        "user_id", str(user.id)
    ).order("recorded_at", desc=True).limit(30).execute().data or []

    agent = registry.get_or_raise("clarifier_agent")
    out = await agent.run(AgentInput(
        user_id=str(user.id),
        persona=user.role.value,
        text="",
        context={
            "journals": journals,
            "conversations": convs,
            "emotion_history": emotions,
        },
    ))
    return {"text": out.text, "synthesis": out.artifacts}


@router.get("/my-profile")
async def get_my_clarification(user: CurrentUser = Depends(get_current_user)):
    """获取我的画像+需求."""
    supabase = get_supabase_admin()
    result = (
        supabase.table("candidate_clarifications")
        .select("*")
        .eq("user_id", str(user.id))
        .maybe_single()
        .execute()
    )
    return result.data or {}


class EmployerClarifyRequest(BaseModel):
    role_id: str
    brief: dict = {}
    spec: dict = {}
    compliance: dict = {}
    policy: dict = {}


@router.post("/synthesize-employer")
async def synthesize_employer(
    body: EmployerClarifyRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """综合用人方人才画像+真实需求."""
    agent = registry.get_or_raise("employer_clarifier_agent")
    out = await agent.run(AgentInput(
        user_id=str(user.id),
        persona=user.role.value,
        text="",
        context={
            "role_id": body.role_id,
            "brief": body.brief,
            "spec": body.spec,
            "compliance": body.compliance,
            "policy": body.policy,
        },
    ))
    return {"text": out.text, "summary": out.artifacts}


@router.get("/role/{role_id}")
async def get_role_clarification(
    role_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """获取岗位的用人方画像+需求."""
    supabase = get_supabase_admin()
    result = (
        supabase.table("employer_clarifications")
        .select("*")
        .eq("role_id", role_id)
        .maybe_single()
        .execute()
    )
    return result.data or {}