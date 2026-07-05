"""Talent Brief API (T204)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agents.registry import registry
from agents.runtime import AgentInput
from api.auth import CurrentUser, get_current_user

logger = logging.getLogger("recruittech.api.talent_brief")
router = APIRouter()


class BriefSubmit(BaseModel):
    text: str


@router.post("/submit")
async def submit_brief(
    body: BriefSubmit,
    user: CurrentUser = Depends(get_current_user),
):
    """老板描述人才框架."""
    agent = registry.get_or_raise("talent_brief_agent")
    out = await agent.run(AgentInput(
        user_id=str(user.id),
        persona=user.role.value,
        text=body.text,
    ))
    return {"text": out.text, "artifacts": out.artifacts}