"""Multi-party Dialog API (T207)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agents.registry import registry
from agents.runtime import AgentInput
from api.auth import CurrentUser, get_current_user

logger = logging.getLogger("recruittech.api.multiparty")
router = APIRouter()


class MultipartyInput(BaseModel):
    inputs: list[dict]   # [{role, message, user_id}]


@router.post("/submit")
async def submit_multiparty(
    body: MultipartyInput,
    user: CurrentUser = Depends(get_current_user),
):
    """多方意见汇总."""
    agent = registry.get_or_raise("multi_party_agent")
    out = await agent.run(AgentInput(
        user_id=str(user.id),
        persona=user.role.value,
        text="",
        context={"inputs": body.inputs},
    ))
    return {"text": out.text, "summary": out.artifacts}