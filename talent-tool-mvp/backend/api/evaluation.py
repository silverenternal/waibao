"""互评 API 端点."""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agents.evaluator.mutual_evaluator import MutualEvaluatorAgent
from agents.registry import registry
from agents.runtime import AgentInput, LLMClient
from api.auth import CurrentUser, get_current_user

logger = logging.getLogger("recruittech.api.evaluation")
router = APIRouter()


class EvaluationScore(BaseModel):
    skill: int = 3
    communication: int = 3
    culture: int = 3
    potential: int = 3
    comment: str = ""


class MutualEvaluationRequest(BaseModel):
    candidate_id: UUID
    role_id: UUID
    candidate_eval: EvaluationScore
    employer_eval: EvaluationScore


@router.post("/mutual")
async def submit_mutual_evaluation(
    body: MutualEvaluationRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """提交双方互评."""
    if registry.get("mutual_evaluator") is None:
        registry.register(MutualEvaluatorAgent(llm=LLMClient()))

    agent = registry.get_or_raise("mutual_evaluator")
    agent_input = AgentInput(
        user_id=str(user.id),
        persona=user.role.value,
        text="",
        context={
            "candidate_id": str(body.candidate_id),
            "role_id": str(body.role_id),
            "candidate_eval": body.candidate_eval.dict(),
            "employer_eval": body.employer_eval.dict(),
        },
    )
    output = await agent.run(agent_input)
    return {
        "text": output.text,
        "result": output.artifacts,
        "success": output.success,
    }