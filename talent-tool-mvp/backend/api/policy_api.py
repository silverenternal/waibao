"""Policy API (T206)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from agents.registry import registry
from agents.runtime import AgentInput
from api.auth import CurrentUser, get_current_user
from api.deps import get_supabase_admin

logger = logging.getLogger("recruittech.api.policy")
router = APIRouter()


class PolicyUpload(BaseModel):
    text: str
    category: str = "other"
    organisation_id: str


@router.post("/upload")
async def upload_policy(
    body: PolicyUpload,
    user: CurrentUser = Depends(get_current_user),
):
    """上传制度文档."""
    agent = registry.get_or_raise("policy_agent")
    out = await agent.run(AgentInput(
        user_id=str(user.id),
        persona=user.role.value,
        text=body.text,
        context={"task_type": "upload", "organisation_id": body.organisation_id, "category": body.category},
    ))
    return {"text": out.text, "items": out.artifacts.get("items", [])}


@router.get("/query")
async def query_policy(
    question: str = Query(...),
    organisation_id: str = Query(...),
    user: CurrentUser = Depends(get_current_user),
):
    """向智能体查询制度(求职者/HR/员工均可)."""
    agent = registry.get_or_raise("policy_agent")
    out = await agent.run(AgentInput(
        user_id=str(user.id),
        persona=user.role.value,
        text=question,
        context={"task_type": "query", "organisation_id": organisation_id},
    ))
    return {"answer": out.text, "matched": out.artifacts.get("matched_policies", [])}


@router.get("/list")
async def list_policies(
    organisation_id: str = Query(...),
    category: str = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
):
    """列出制度列表."""
    supabase = get_supabase_admin()
    query = supabase.table("company_policies").select("id, title, category, content, effective_from, created_at").eq(
        "organisation_id", organisation_id
    )
    if category:
        query = query.eq("category", category)
    result = query.order("created_at", desc=True).limit(100).execute()
    return {"data": result.data or []}