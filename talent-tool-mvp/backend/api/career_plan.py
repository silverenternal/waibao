"""Career Plan API (T105)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from agents.registry import registry
from agents.runtime import AgentInput
from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin

logger = logging.getLogger("recruittech.api.career_plan")
router = APIRouter()


@router.post("/generate")
async def generate_plan(user: CurrentUser = Depends(get_current_user)):
    """基于最新画像生成职业规划."""
    supabase = get_supabase_admin()

    # 拉取画像
    profile = await _get_profile(str(user.id), supabase)
    needs = await _get_needs(str(user.id), supabase)

    agent = registry.get_or_raise("career_planner_agent")
    out = await agent.run(AgentInput(
        user_id=str(user.id),
        persona=user.role.value,
        text="",
        context={"profile": profile, "needs": needs},
    ))
    return {"text": out.text, "plan": out.artifacts}


@router.get("/current")
async def get_current_plan(user: CurrentUser = Depends(get_current_user)):
    """获取当前规划."""
    supabase = get_supabase_admin()
    result = (
        supabase.table("career_plans")
        .select("*")
        .eq("user_id", str(user.id))
        .maybe_single()
        .execute()
    )
    return result.data or {}


async def _get_profile(user_id: str, supabase) -> dict:
    """拉取最新画像."""
    # candidates 表
    cand = supabase.table("candidates").select("*").eq("created_by", user_id).maybe_single().execute().data or {}
    # memory 中 profile
    mem = supabase.table("agent_memory").select("value").eq("user_id", user_id).eq(
        "scope", "long_term"
    ).eq("key", "profile").maybe_single().execute().data or {}
    return {**cand, **(mem.get("value") or {})}


async def _get_needs(user_id: str, supabase) -> dict:
    """拉取真实需求."""
    clar = (
        supabase.table("candidate_clarifications")
        .select("*")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    ).data or {}
    return {
        "explicit_needs": clar.get("explicit_needs", []),
        "implicit_needs": clar.get("implicit_needs", []),
        "must_haves": clar.get("must_haves", []),
    }