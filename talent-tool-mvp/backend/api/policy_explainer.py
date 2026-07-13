"""T3706 policy explainer API."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.policy_explainer import explain_policy

logger = logging.getLogger("recruittech.api.policy_explainer")

router = APIRouter(prefix="/api/policy-explainer", tags=["policy_explainer"])


class ExplainIn(BaseModel):
    title: str
    content: str = Field(..., min_length=1)


@router.post("/explain")
async def explain(req: ExplainIn) -> Dict[str, Any]:
    if not req.content.strip():
        raise HTTPException(400, "content empty")
    out = explain_policy(req.title, req.content)
    return {"title": req.title, **out.to_dict()}
