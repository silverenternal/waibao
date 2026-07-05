"""Job Spec API (T205)."""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agents.registry import registry
from agents.runtime import AgentInput
from api.auth import CurrentUser, get_current_user

logger = logging.getLogger("recruittech.api.job_spec")
router = APIRouter()


class SpecSubmit(BaseModel):
    text: str
    role_id: Optional[UUID] = None


@router.post("/submit")
async def submit_spec(
    body: SpecSubmit,
    user: CurrentUser = Depends(get_current_user),
):
    """部门负责人提交 JD 细节."""
    agent = registry.get_or_raise("job_spec_agent")
    out = await agent.run(AgentInput(
        user_id=str(user.id),
        persona=user.role.value,
        text=body.text,
        context={"role_id": str(body.role_id)} if body.role_id else {},
    ))
    return {"text": out.text, "draft_jd": out.artifacts.get("draft_jd"), "artifacts": out.artifacts}