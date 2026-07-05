"""Vision Agent API (T203)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agents.registry import registry
from agents.runtime import AgentInput
from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin

logger = logging.getLogger("recruittech.api.vision")
router = APIRouter()


class VisionSubmit(BaseModel):
    text: str


@router.post("/submit")
async def submit_vision(
    body: VisionSubmit,
    user: CurrentUser = Depends(get_current_user),
):
    """老板提交愿景/规划/战略/战术."""
    agent = registry.get_or_raise("vision_agent")
    out = await agent.run(AgentInput(
        user_id=str(user.id),
        persona=user.role.value,
        text=body.text,
        context={"organisation_id": str(user.id)},
    ))
    return {
        "text": out.text,
        "artifacts": out.artifacts,
    }


@router.get("/strategy-map")
async def get_strategy_map(
    organisation_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """获取组织战略地图."""
    supabase = get_supabase_admin()
    result = (
        supabase.table("company_strategy")
        .select("*")
        .eq("organisation_id", organisation_id)
        .eq("status", "active")
        .order("created_at", desc=True)
        .execute()
    )
    items = result.data or []

    # 按 level 分组
    by_level = {"vision": [], "planning": [], "strategy": [], "tactic": []}
    for item in items:
        by_level.setdefault(item.get("level", "tactic"), []).append(item)
    return {"strategy_map": by_level}