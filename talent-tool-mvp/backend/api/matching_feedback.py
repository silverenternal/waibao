"""T3710 - matching feedback API."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.matching_feedback import (
    compute_hit_rate, aggregate_feedback, collect_feedback,
    FeedbackEntry, FUNNEL_STAGES,
)

logger = logging.getLogger("recruittech.api.matching_feedback")

router = APIRouter(prefix="/api/matching-feedback", tags=["matching_feedback"])


class EventsIn(BaseModel):
    events: List[Dict[str, Any]] = Field(default_factory=list)


@router.post("/hit-rate")
async def hit_rate(req: EventsIn) -> Dict[str, Any]:
    rep = compute_hit_rate(req.events)
    return rep.to_dict()


class FeedbackIn(BaseModel):
    candidate_id: str
    role_id: str
    label: str
    rating: int
    note: str = ""
    feedback_by: Optional[str] = None


@router.post("/feedback")
async def feedback(req: FeedbackIn) -> Dict[str, Any]:
    try:
        entry = collect_feedback(
            candidate_id=req.candidate_id,
            role_id=req.role_id,
            label=req.label,
            rating=req.rating,
            note=req.note,
            feedback_by=req.feedback_by,
            now_iso=datetime.utcnow().isoformat(),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "feedback": entry.to_dict()}


class AggregateIn(BaseModel):
    entries: List[Dict[str, Any]] = Field(default_factory=list)


@router.post("/aggregate")
async def aggregate(req: AggregateIn) -> Dict[str, Any]:
    objs = [FeedbackEntry(**e) for e in req.entries]
    summary = aggregate_feedback(objs)
    return summary


@router.get("/funnel-stages")
async def stages() -> Dict[str, Any]:
    return {"stages": FUNNEL_STAGES}
