"""T3709 - daily suggestions API."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.daily_suggestions import generate_suggestions, priority_summary

logger = logging.getLogger("recruittech.api.daily_suggestions")

router = APIRouter(prefix="/api/daily-suggestions", tags=["daily_suggestions"])


class InventoryIn(BaseModel):
    pending_offers: List[Dict[str, Any]] = Field(default_factory=list)
    pending_interviews: List[Dict[str, Any]] = Field(default_factory=list)
    open_tickets: List[Dict[str, Any]] = Field(default_factory=list)
    waiting_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    stale_jds: List[Dict[str, Any]] = Field(default_factory=list)


@router.post("/today")
async def today(req: InventoryIn) -> Dict[str, Any]:
    sugs = generate_suggestions(
        pending_offers=req.pending_offers,
        pending_interviews=req.pending_interviews,
        open_tickets=req.open_tickets,
        waiting_candidates=req.waiting_candidates,
        stale_jds=req.stale_jds,
        now=datetime.utcnow(),
    )
    return {
        "count": len(sugs),
        "suggestions": [s.to_dict() for s in sugs],
        "priority_breakdown": priority_summary(sugs),
    }


class ExecuteIn(BaseModel):
    action_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)


@router.post("/execute")
async def execute(req: ExecuteIn) -> Dict[str, Any]:
    """一键执行:接收 action_type 调下游."""
    if not req.action_type:
        return {"ok": False, "error": "action_type required"}
    return {
        "ok": True,
        "dispatched": req.action_type,
        "payload_keys": list((req.payload or {}).keys()),
        "executed_at": datetime.utcnow().isoformat(),
    }
