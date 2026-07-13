"""T3708 consensus v2 API."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.consensus_v2 import compute_consensus, level_for, STRONG_THRESHOLD, WEAK_THRESHOLD

logger = logging.getLogger("recruittech.api.consensus_v2")

router = APIRouter(prefix="/api/consensus-v2", tags=["consensus_v2"])


class ConsensusIn(BaseModel):
    dimension_ratings: Dict[str, List[float]] = Field(default_factory=dict)
    notes_by_dim: Optional[Dict[str, List[str]]] = None


@router.post("/compute")
async def compute(req: ConsensusIn) -> Dict[str, Any]:
    if not req.dimension_ratings:
        return {"error": "dimension_ratings required"}
    rep = compute_consensus(req.dimension_ratings, req.notes_by_dim)
    return rep.to_dict()


@router.get("/thresholds")
async def thresh() -> Dict[str, Any]:
    return {"strong": STRONG_THRESHOLD, "weak": WEAK_THRESHOLD, "fuzzy_max": WEAK_THRESHOLD}
